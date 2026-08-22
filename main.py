import asyncio
import json
import mimetypes
import os
import sys
import threading
import time
import urllib.parse
import urllib.request
import webbrowser
from socketserver import ThreadingMixIn
from http.server import HTTPServer, BaseHTTPRequestHandler
from typing import Dict, Any, List

try:
    import yaml
except Exception:
    yaml = None

from ssh_deployer import SSHDeployer, run_deployment

PORT = 8000
HOST = "127.0.0.1"
APP_DIR = os.path.dirname(os.path.abspath(__file__))
BACKUP_FILE = os.path.join(APP_DIR, "setup_backup.yml")
SERVERS_FILE = os.path.join(APP_DIR, "servers.json")

DEPLOY_LOCK = threading.Lock()
LOG_CONDITION = threading.Condition(DEPLOY_LOCK)
CACHE_LOCK = threading.Lock()

active_logs: List[Dict[str, str]] = []
is_deploying = False
deploy_status = "idle"
deploy_result: Dict[str, Any] = {}
cancel_requested = False

XUI_TOKEN_URL = "https://ghcr.io/token?scope=repository:mhsanaei/3x-ui:pull"
XUI_TAGS_URL = "https://ghcr.io/v2/mhsanaei/3x-ui/tags/list?n=1000"
XUI_UA = "3x-ui-bootstrUp"
XUI_CACHE: Dict[str, Any] = {"data": None, "ts": 0.0}

def _xui_ver_key(tag: str) -> List[int]:
    base = tag[1:] if tag.startswith("v") else tag
    return [int(p) if p.isdigit() else -1 for p in base.split(".")]

def fetch_xui_versions() -> List[str]:
    now = time.time()
    with CACHE_LOCK:
        if XUI_CACHE["data"] is not None and now - XUI_CACHE["ts"] < 300:
            return list(XUI_CACHE["data"])

    req = urllib.request.Request(XUI_TOKEN_URL, headers={"User-Agent": XUI_UA})
    with urllib.request.urlopen(req, timeout=10) as resp:
        token = json.loads(resp.read().decode("utf-8")).get("token", "")

    headers = {"Authorization": f"Bearer {token}", "User-Agent": XUI_UA}
    req = urllib.request.Request(XUI_TAGS_URL, headers=headers)
    with urllib.request.urlopen(req, timeout=15) as resp:
        data = json.loads(resp.read().decode("utf-8"))

    tags = data.get("tags") or []
    seen: Dict[str, str] = {}
    for t in tags:
        base = t[1:] if t.startswith("v") else t
        if base not in seen or seen[base].startswith("v"):
            seen[base] = t

    versions = sorted(seen.keys(), key=_xui_ver_key, reverse=True)
    if "latest" in versions:
        versions.remove("latest")
        versions.insert(0, "latest")

    with CACHE_LOCK:
        XUI_CACHE["data"] = versions
        XUI_CACHE["ts"] = now
    return versions

UPDATE_CHECK_URL = "https://github.com/honmiv/3x-ui-bootstRUp/archive/refs/heads/master.tar.gz"
UPDATE_CACHE: Dict[str, Any] = {"data": None, "ts": 0.0, "err": None, "err_ts": 0.0}
UPDATE_CACHE_TTL = 300
UPDATE_ERR_TTL = 60
EXCLUDED_DIRS = {".git", "__pycache__", ".python_env", "backups_panel", "backups_sub_server", "working", "backup"}


def _is_code_file(rel: str) -> bool:
    parts = rel.split("/")
    if any(p in EXCLUDED_DIRS for p in parts):
        return False
    if rel in ("servers.json", "setup_backup.yml") or rel.endswith(".pyc"):
        return False
    return True


def _is_binary(data: bytes) -> bool:
    return b"\0" in data[:2048]


def _local_code_files() -> Dict[str, bytes]:
    result: Dict[str, bytes] = {}
    for dirpath, dirnames, filenames in os.walk(APP_DIR):
        dirnames[:] = [d for d in dirnames if d not in EXCLUDED_DIRS]
        for fn in filenames:
            full = os.path.join(dirpath, fn)
            rel = os.path.relpath(full, APP_DIR).replace(os.sep, "/")
            if not _is_code_file(rel):
                continue
            try:
                with open(full, "rb") as f:
                    data = f.read()
            except Exception:
                continue
            if _is_binary(data):
                continue
            result[rel] = data
    return result


def _remote_code_files() -> Dict[str, bytes]:
    import io
    import tarfile

    req = urllib.request.Request(UPDATE_CHECK_URL, headers={"User-Agent": XUI_UA})
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = resp.read()

    result: Dict[str, bytes] = {}
    with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as tf:
        for member in tf.getmembers():
            if not member.isfile():
                continue
            parts = member.name.split("/")
            if len(parts) < 2:
                continue
            rel = "/".join(parts[1:])
            if not _is_code_file(rel):
                continue
            fobj = tf.extractfile(member)
            if fobj is None:
                continue
            raw = fobj.read()
            if _is_binary(raw):
                continue
            result[rel] = raw
    return result


def _fingerprint(files: Dict[str, bytes]) -> str:
    import hashlib

    h = hashlib.sha256()
    for rel in sorted(files):
        h.update(rel.encode("utf-8", "replace"))
        h.update(b"\0")
        h.update(files[rel])
    return h.hexdigest()


def check_for_update() -> Dict[str, Any]:
    now = time.time()
    with CACHE_LOCK:
        if UPDATE_CACHE["data"] is not None and now - UPDATE_CACHE["ts"] < UPDATE_CACHE_TTL:
            return dict(UPDATE_CACHE["data"])
        if UPDATE_CACHE["err"] is not None and now - UPDATE_CACHE["err_ts"] < UPDATE_ERR_TTL:
            return {"update_available": False, "error": UPDATE_CACHE["err"]}

    try:
        local = _local_code_files()
        remote = _remote_code_files()
        local_fp = _fingerprint(local)
        remote_fp = _fingerprint(remote)
        result = {
            "update_available": local_fp != remote_fp,
            "local_version": local_fp[:12],
            "latest_version": remote_fp[:12],
            "files": {"local": len(local), "remote": len(remote)},
        }
        with CACHE_LOCK:
            UPDATE_CACHE["data"] = result
            UPDATE_CACHE["ts"] = now
            UPDATE_CACHE["err"] = None
        return result
    except Exception as e:
        with CACHE_LOCK:
            UPDATE_CACHE["err"] = str(e)
            UPDATE_CACHE["err_ts"] = now
        return {"update_available": False, "error": str(e)}

def is_cancel_requested() -> bool:
    with DEPLOY_LOCK:
        return cancel_requested

def log_event(message: str, level: str = "info"):
    with LOG_CONDITION:
        active_logs.append({"message": message, "level": level})
        LOG_CONDITION.notify_all()

def cli_ext() -> str:
    ext = os.environ.get("XUI_CLI_EXT", "").strip().lstrip(".").lower()
    if ext in ("sh", "bat", "cmd", "ps1"):
        return ext
    return "bat" if sys.platform.startswith("win") else "sh"

def cli_script_path(base_name: str) -> str:
    base_dir = os.path.dirname(os.path.abspath(__file__))
    preferred = cli_ext()
    if preferred in ("bat", "cmd"):
        candidates = [f"{base_name}.bat", f"{base_name}.cmd"]
        if preferred == "cmd":
            candidates.reverse()
    else:
        candidates = [f"{base_name}.{preferred}"]
    candidates += [f"{base_name}.sh", f"{base_name}.cmd", f"{base_name}.bat", f"{base_name}.ps1"]
    for name in candidates:
        p = os.path.join(base_dir, name)
        if os.path.exists(p):
            return p
    return ""

def launch_script(script_path: str) -> None:
    import subprocess
    ext = os.path.splitext(script_path)[1].lower()
    script_dir = os.path.dirname(os.path.abspath(script_path))
    if ext == ".ps1":
        subprocess.Popen(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", script_path],
            cwd=script_dir, start_new_session=True,
        )
    elif ext == ".sh":
        os.chmod(script_path, 0o755)
        subprocess.Popen(["bash", script_path], cwd=script_dir, start_new_session=True)
    else:
        subprocess.Popen([script_path], cwd=script_dir, start_new_session=True)

def load_backup_config() -> Dict[str, Any]:
    if not os.path.exists(BACKUP_FILE):
        return {}

    def _is_sensitive_key(key: Any) -> bool:
        normalized = str(key).lower()
        return "password" in normalized or normalized.endswith("_key")

    def _strip_sensitive_values(data: Dict[str, Any]) -> Dict[str, Any]:
        return {
            key: value for key, value in data.items()
            if not _is_sensitive_key(key)
        }

    def _flatten_loaded_config(raw: Any) -> Dict[str, Any]:
        if not isinstance(raw, dict):
            return {}
        flat: Dict[str, Any] = {}
        for key, value in raw.items():
            if isinstance(value, dict):
                flat.update(value)
            else:
                flat[key] = value
        return flat

    if yaml is None:
        return {}

    try:
        with open(BACKUP_FILE, "r", encoding="utf-8") as f:
            content = f.read()
        loaded = yaml.safe_load(content) or {}
        data = _flatten_loaded_config(loaded)
        if not data:
            return {}
        return _strip_sensitive_values(data)
    except Exception:
        return {}

def save_backup_config(data: Dict[str, Any]) -> bool:
    try:
        if yaml is None:
            raise RuntimeError("PyYAML is unavailable")

        def pick(*keys):
            result = {}
            for k in keys:
                if k in data:
                    result[k] = data[k]
            return result

        payload = {
            "common": pick("deploy_mode", "is_cascade"),
            "freedom_node": pick(
                "freedom_host", "freedom_host_for_ssh", "freedom_port", "freedom_user", "freedom_password",
                "freedom_key", "freedom_auth_type", "freedom_xui_username",
                "freedom_xui_password", "freedom_sub_secret", "freedom_client_name",
                "freedom_xui_version"
            ),
            "proxy_node": pick(
                "proxy_host", "proxy_host_for_ssh", "proxy_port", "proxy_user", "proxy_password", "proxy_key",
                "proxy_auth_type", "proxy_xui_username", "proxy_xui_password",
                "proxy_sub_secret", "proxy_client_tcp_list", "proxy_client_xhttp_list",
                "foreign_sub_url", "proxy_xui_version"
            ),
            "standard_node": pick("vps_host", "vps_port", "vps_user", "vps_password", "vps_key", "vps_auth_type"),
            "sub_server": pick(
                "sub_vps_host", "sub_vps_port", "sub_vps_user", "sub_vps_password",
                "sub_vps_key", "sub_auth_type", "sub_domain", "sub_secret_path",
                "sub_russian_url", "sub_foreign_url", "sub_proxy_clients",
                "sub_freedom_clients", "sub_admin_user", "sub_backup_name",
                "rollback_sub_backup_file"
            ),
            "backup_node": pick(
                "backup_vps_host", "backup_vps_port", "backup_vps_user",
                "backup_vps_password", "backup_vps_key", "backup_auth_type", "backup_name"
            ),
            "recovery_node": pick(
                "recovery_vps_host", "recovery_vps_port", "recovery_vps_user",
                "recovery_vps_password", "recovery_vps_key", "recovery_auth_type",
                "recovery_backup_file", "recovery_xui_username"
            ),
            "panel_and_clients": pick(
                "xui_username", "xui_password", "sub_secret", "client_tcp_list",
                "client_xhttp_list", "foreign_sub_url", "xui_version"
            ),
            "update_node": pick(
                "update_vps_host", "update_vps_port", "update_vps_user",
                "update_vps_password", "update_vps_key", "update_auth_type",
                "update_xui_version"
            ),
            "ui_state": {k: data[k] for k in data if k.startswith("ui_")},
        }

        # Drop empty groups to keep the file compact and readable.
        payload = {k: v for k, v in payload.items() if v}

        # Passwords and private keys must never be persisted in
        # setup_backup.yml, even if new fields are added to the frontend.
        payload = {
            section: {
                key: value for key, value in values.items()
                if "password" not in str(key).lower()
                and not str(key).lower().endswith("_key")
            }
            for section, values in payload.items()
        }
        payload = {section: values for section, values in payload.items() if values}

        with open(BACKUP_FILE, "w", encoding="utf-8") as f:
            f.write("# Auto-generated setup backup\n")
            yaml.safe_dump(payload, f, allow_unicode=True, sort_keys=False, default_flow_style=False)
        return True
    except Exception as e:
        log_event(f"[ERROR] Failed to save setup_backup.yml: {e}", "error")
        return False

def list_backup_files(folder: str = "backups_panel") -> List[Dict[str, Any]]:
    backups_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), folder)
    if not os.path.exists(backups_dir):
        return []
    result = []
    try:
        for fname in os.listdir(backups_dir):
            if fname.startswith("."):
                continue
            if any(fname.endswith(ext) for ext in [".tar.gz", ".tgz", ".zip", ".tar"]):
                fpath = os.path.join(backups_dir, fname)
                if os.path.isfile(fpath):
                    st = os.stat(fpath)
                    size_mb = round(st.st_size / (1024 * 1024), 2)
                    size_str = f"{size_mb} MB" if size_mb >= 0.1 else f"{round(st.st_size / 1024, 1)} KB"
                    import datetime
                    mtime_str = datetime.datetime.fromtimestamp(st.st_mtime).strftime("%Y-%m-%d %H:%M:%S")
                    result.append({
                        "name": fname,
                        "size": size_str,
                        "mtime": mtime_str,
                        "mtime_ts": st.st_mtime
                    })
        result.sort(key=lambda x: x["mtime_ts"], reverse=True)
    except Exception:
        pass
    return result

class WebUIHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass

    def send_json(self, data: Dict[str, Any], status: int = 200):
        body = json.dumps(data, ensure_ascii=False).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        url_path = urllib.parse.urlparse(self.path).path

        if url_path == "/api/config":
            self.send_json(load_backup_config())
            return

        if url_path == "/api/xui_versions":
            try:
                self.send_json({"versions": fetch_xui_versions()})
            except Exception as e:
                self.send_json({"versions": ["latest", "3.6.0"], "error": str(e)})
            return

        if url_path == "/api/update_check":
            self.send_json(check_for_update())
            return

        if url_path == "/api/backups":
            params = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            folder = params.get("folder", ["backups_panel"])[0]
            if folder == "backups_sub_server":
                self.send_json(list_backup_files("backups_sub_server"))
            else:
                self.send_json(list_backup_files("backups_panel"))
            return

        if url_path == "/api/status":
            with DEPLOY_LOCK:
                status_payload = {
                    "deploying": is_deploying,
                    "status": deploy_status,
                    "logs_count": len(active_logs),
                    "result": dict(deploy_result)
                }
            self.send_json(status_payload)
            return

        if url_path == "/api/servers":
            if not os.path.exists(SERVERS_FILE):
                self.send_json([])
                return
            try:
                with open(SERVERS_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                self.send_json(data)
            except Exception:
                self.send_json([])
            return

        if url_path == "/api/deploy/logs":
            self.send_response(200)
            self.send_header('Content-Type', 'text/event-stream')
            self.send_header('Cache-Control', 'no-cache')
            self.send_header('Connection', 'keep-alive')
            self.end_headers()

            sent_index = 0
            while True:
                with LOG_CONDITION:
                    while is_deploying and sent_index >= len(active_logs):
                        LOG_CONDITION.wait(timeout=1.0)

                    new_items = list(active_logs[sent_index:])
                    still_deploying = is_deploying
                    final_status = deploy_status

                for item in new_items:
                    event_data = f"data: {json.dumps(item, ensure_ascii=False)}\n\n"
                    try:
                        self.wfile.write(event_data.encode('utf-8'))
                        self.wfile.flush()
                        sent_index += 1
                    except Exception:
                        return

                if not still_deploying and sent_index >= len(active_logs):
                    done_item = {
                        "message": "[DONE] Installation process completed.",
                        "level": "success",
                        "event": "done",
                        "status": final_status
                    }
                    event_data = f"data: {json.dumps(done_item, ensure_ascii=False)}\n\n"
                    try:
                        self.wfile.write(event_data.encode('utf-8'))
                        self.wfile.flush()
                    except Exception:
                        pass
                    break
            return

        if url_path == "/":
            url_path = "/index.html"

        if url_path.startswith("/resources/"):
            base_dir = os.path.join(os.path.dirname(__file__), "resources")
            target_file = os.path.abspath(os.path.join(base_dir, url_path[len("/resources/"):].lstrip("/")))
        else:
            base_dir = os.path.join(os.path.dirname(__file__), "panel", "static")
            target_file = os.path.abspath(os.path.join(base_dir, url_path.lstrip("/")))

        if not (target_file == base_dir or target_file.startswith(base_dir + os.sep)) or not os.path.isfile(target_file):
            self.send_response(404)
            self.end_headers()
            self.wfile.write(b"404 Not Found")
            return

        mime_type, _ = mimetypes.guess_type(target_file)
        if not mime_type:
            mime_type = "application/octet-stream"

        try:
            with open(target_file, "rb") as f:
                content = f.read()
            self.send_response(200)
            self.send_header("Content-Type", mime_type)
            self.send_header("Content-Length", str(len(content)))
            self.send_header("Cache-Control", "no-store, no-cache, must-revalidate, max-age=0")
            self.send_header("Pragma", "no-cache")
            self.send_header("Expires", "0")
            self.end_headers()
            self.wfile.write(content)
        except Exception as e:
            self.send_response(500)
            self.end_headers()
            self.wfile.write(str(e).encode('utf-8'))

    def do_POST(self):
        global is_deploying, active_logs, deploy_status, deploy_result, cancel_requested
        url_path = urllib.parse.urlparse(self.path).path
        content_len = int(self.headers.get('Content-Length', 0))
        post_body = self.rfile.read(content_len)

        try:
            payload = json.loads(post_body.decode('utf-8')) if post_body else {}
        except json.JSONDecodeError:
            self.send_json({"error": "Invalid JSON"}, 400)
            return

        if url_path == "/api/servers":
            try:
                with open(SERVERS_FILE, "w", encoding="utf-8") as f:
                    json.dump(payload, f, ensure_ascii=False, indent=2)
                self.send_json({"ok": True})
            except Exception as e:
                self.send_json({"error": str(e)}, 500)
            return

        if url_path == "/api/config":
            if save_backup_config(payload):
                self.send_json({"ok": True})
            else:
                self.send_json({"ok": False, "error": "Failed to save setup_backup.yml"}, 500)
            return

        if url_path == "/api/ssh/test":
            host = (payload.get("vps_host") or payload.get("backup_vps_host") or payload.get("recovery_vps_host") or payload.get("update_vps_host") or payload.get("sub_vps_host") or "").strip()
            port = int(payload.get("vps_port") or payload.get("backup_vps_port") or payload.get("recovery_vps_port") or payload.get("update_vps_port") or payload.get("sub_vps_port") or 22)
            user = (payload.get("vps_user") or payload.get("backup_vps_user") or payload.get("recovery_vps_user") or payload.get("update_vps_user") or payload.get("sub_vps_user") or "root").strip()
            password = payload.get("vps_password") if payload.get("vps_password") is not None else (payload.get("backup_vps_password") if payload.get("backup_vps_password") is not None else (payload.get("recovery_vps_password") if payload.get("recovery_vps_password") is not None else (payload.get("update_vps_password") if payload.get("update_vps_password") is not None else payload.get("sub_vps_password", ""))))
            key_data = payload.get("vps_key") if payload.get("vps_key") is not None else (payload.get("backup_vps_key") if payload.get("backup_vps_key") is not None else (payload.get("recovery_vps_key") if payload.get("recovery_vps_key") is not None else (payload.get("update_vps_key") if payload.get("update_vps_key") is not None else payload.get("sub_vps_key", ""))))

            if not host:
                self.send_json({"ok": False, "message": "Host address is required"}, 400)
                return

            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

            async def run_test():
                async with SSHDeployer(host, port, user, password, key_data) as deployer:
                    return await deployer.test_connection()

            try:
                ok, msg = loop.run_until_complete(run_test())
                self.send_json({"ok": ok, "message": msg})
            except Exception as e:
                self.send_json({"ok": False, "message": f"Test exception: {str(e)}"})
            finally:
                loop.close()
            return

        if url_path == "/api/deploy/stop":
            with DEPLOY_LOCK:
                if is_deploying:
                    cancel_requested = True
                    deploy_status = "cancelled"
                    already_running = True
                else:
                    already_running = False
            if already_running:
                log_event("[CANCEL] Отмена процесса затребована пользователем...", "warning")
                self.send_json({"ok": True, "message": "Deployment cancellation requested"})
            else:
                self.send_json({"ok": False, "message": "No deployment currently running"}, 400)
            return

        if url_path == "/api/deploy":
            with DEPLOY_LOCK:
                if is_deploying:
                    self.send_json({"ok": False, "message": "Deployment already in progress"}, 400)
                    return

                cancel_requested = False
                active_logs.clear()
                deploy_result = {}
                is_deploying = True
                deploy_status = "running"
                LOG_CONDITION.notify_all()

            save_backup_config(payload)

            def start_deploy_bg(cfg):
                global is_deploying, deploy_status, deploy_result, cancel_requested
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                try:
                    success, res_data = loop.run_until_complete(run_deployment(cfg, log_event, cancel_check=is_cancel_requested))
                    with LOG_CONDITION:
                        if cancel_requested:
                            deploy_status = "cancelled"
                            deploy_result = {}
                        else:
                            deploy_status = "completed" if success else "failed"
                            deploy_result = res_data if success else {}
                except Exception as e:
                    log_event(f"Unhandled deploy exception: {str(e)}", "error")
                    with LOG_CONDITION:
                        deploy_status = "failed"
                finally:
                    with LOG_CONDITION:
                        is_deploying = False
                        LOG_CONDITION.notify_all()
                    loop.close()

            t = threading.Thread(target=start_deploy_bg, args=(payload,), daemon=True)
            t.start()

            self.send_json({"ok": True, "message": "Deployment started"})
            return

        if url_path == "/api/update_sources":
            with DEPLOY_LOCK:
                if is_deploying:
                    self.send_json({"ok": False, "message": "Нельзя обновлять исходники во время развертывания"}, 400)
                    return

            self.send_json({"ok": True, "message": "Запуск обновления исходников..."})

            def run_update_bg():
                time.sleep(0.5)
                script_path = cli_script_path("update_sources")
                if script_path:
                    launch_script(script_path)
                time.sleep(0.5)
                os._exit(0)

            t = threading.Thread(target=run_update_bg, daemon=True)
            t.start()
            return

        if url_path == "/api/restart":
            with DEPLOY_LOCK:
                if is_deploying:
                    self.send_json({"ok": False, "message": "Нельзя перезапустить сервер во время развертывания"}, 400)
                    return

            self.send_json({"ok": True, "message": "Перезапуск сервера..."})

            server_ref = self.server

            def run_restart_bg():
                time.sleep(0.3)
                try:
                    server_ref.socket.close()
                except Exception:
                    pass
                time.sleep(0.3)
                script_path = cli_script_path("start_3x_ui_deployment_manager")
                if script_path:
                    launch_script(script_path)
                os._exit(0)

            t = threading.Thread(target=run_restart_bg, daemon=True)
            t.start()
            return

        if url_path == "/api/shutdown":
            with DEPLOY_LOCK:
                if is_deploying:
                    self.send_json({"ok": False, "message": "Нельзя выключить сервер во время развертывания"}, 400)
                    return

            self.send_json({"ok": True, "message": "Выключение сервера..."})

            server_ref = self.server

            def run_shutdown_bg():
                time.sleep(0.3)
                try:
                    server_ref.socket.close()
                except Exception:
                    pass
                time.sleep(0.2)
                os._exit(0)

            t = threading.Thread(target=run_shutdown_bg, daemon=True)
            t.start()
            return

        self.send_json({"error": "Endpoint not found"}, 404)

    def do_DELETE(self):
        url_path = urllib.parse.urlparse(self.path).path
        if url_path == "/api/servers/reset":
            try:
                if os.path.exists(SERVERS_FILE):
                    os.remove(SERVERS_FILE)
                self.send_json({"ok": True})
            except Exception as e:
                self.send_json({"error": str(e)}, 500)
            return

        self.send_json({"error": "Endpoint not found"}, 404)


class ThreadingHTTPServer(ThreadingMixIn, HTTPServer):
    """Serve long-lived SSE connections without blocking other UI requests."""

    daemon_threads = True

def main():
    server_address = (HOST, PORT)
    httpd = None
    for attempt in range(5):
        try:
            httpd = ThreadingHTTPServer(server_address, WebUIHandler)
            break
        except OSError as e:
            if attempt < 4 and e.errno in (48, 98):
                import time
                time.sleep(0.5)
            else:
                raise

    url = f"http://{HOST}:{PORT}"

    print(f"==================================================")
    print(f"  3X UI Deployment Manager Web UI running at: {url}")
    print(f"  Open {url} in browser")
    print(f"  Press Ctrl+C to stop local server")
    print(f"==================================================")

    try:
        null_fd = os.open(os.devnull, os.O_RDWR)
        stderr_fd = os.dup(2)
        stdout_fd = os.dup(1)
        os.dup2(null_fd, 2)
        os.dup2(null_fd, 1)
        try:
            webbrowser.open(url)
        finally:
            os.dup2(stderr_fd, 2)
            os.dup2(stdout_fd, 1)
            os.close(stderr_fd)
            os.close(stdout_fd)
            os.close(null_fd)
    except Exception:
        pass

    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down server...")
        httpd.server_close()
        sys.exit(0)

if __name__ == "__main__":
    main()
