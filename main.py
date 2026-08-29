import asyncio
import json
import mimetypes
import os
import re
import signal
import socket
import subprocess
import sys
import threading
import time
import urllib.parse
import urllib.request
import webbrowser
from socketserver import ThreadingMixIn
from http.server import HTTPServer, BaseHTTPRequestHandler
from typing import Dict, Any, List, Optional, Tuple

from ssh_deployer import SSHDeployer, run_deployment, validate_deployment_config
import decoy_manager

PORT = int(os.environ.get("PORT", 8000))
HOST = "127.0.0.1"
APP_DIR = os.path.dirname(os.path.abspath(globals()["__file__"])) if globals().get("__file__") else os.path.abspath(os.path.dirname(sys.argv[0]) if sys.argv and sys.argv[0] else os.getcwd())
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

UPDATE_CHECK_URL = os.environ.get(
    "UPDATE_CHECK_URL",
    "https://github.com/honmiv/3x-ui-bootstRUp/archive/refs/heads/master.tar.gz"
)
UPDATE_CACHE: Dict[str, Any] = {"data": None, "ts": 0.0, "err": None, "err_ts": 0.0}
UPDATE_CACHE_TTL = 300
UPDATE_ERR_TTL = 60
EXCLUDED_DIRS = {".git", "__pycache__", ".python_env", "backups_panel", "backups_sub_server", "working", "backup", ".cache", ".pytest_cache"}


def _is_code_file(rel: str) -> bool:
    parts = rel.split("/")
    if any(p in EXCLUDED_DIRS for p in parts):
        return False
    if rel in ("servers.json", "setup_backup.yml") or rel.endswith("happ-routing.json") or rel.endswith(".pyc"):
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


def _compute_changelog_diff(local_raw: bytes, remote_raw: bytes) -> str:
    local_text = (local_raw or b"").decode("utf-8", errors="replace").strip()
    remote_text = (remote_raw or b"").decode("utf-8", errors="replace").strip()

    if not remote_text:
        return ""
    if not local_text:
        return remote_text
    if local_text == remote_text:
        return ""

    local_first_line = ""
    for line in local_text.splitlines():
        if line.strip():
            local_first_line = line
            break

    if local_first_line and local_first_line in remote_text:
        pos = remote_text.find(local_first_line)
        if pos > 0:
            diff = remote_text[:pos].strip()
            if diff:
                return diff

    if remote_text.startswith(local_text):
        diff = remote_text[len(local_text):].strip()
        if diff:
            return diff

    import difflib

    local_lines = [l + "\n" for l in local_text.splitlines()]
    remote_lines = [l + "\n" for l in remote_text.splitlines()]
    added = [line[2:] for line in difflib.ndiff(local_lines, remote_lines) if line.startswith("+ ")]
    if added:
        return "".join(added).strip()

def _parse_remote_html(remote: Dict[str, bytes], filename: str) -> str:
    raw = remote.get(filename) or b""
    return raw.decode("utf-8", errors="replace").strip()


def check_for_update(force: bool = False) -> Dict[str, Any]:
    now = time.time()
    with CACHE_LOCK:
        if not force and UPDATE_CACHE["data"] is not None and now - UPDATE_CACHE["ts"] < UPDATE_CACHE_TTL:
            return dict(UPDATE_CACHE["data"])
        if not force and UPDATE_CACHE["err"] is not None and now - UPDATE_CACHE["err_ts"] < UPDATE_ERR_TTL:
            return {"update_available": False, "error": UPDATE_CACHE["err"]}

    try:
        local = _local_code_files()
        remote = _remote_code_files()
        local_fp = _fingerprint(local)
        remote_fp = _fingerprint(remote)
        local_changelog = local.get("change.log", b"")
        remote_changelog = remote.get("change.log", b"")
        changelog_diff = _compute_changelog_diff(local_changelog, remote_changelog)
        remote_update_banner = _parse_remote_html(remote, "update_banner.html")
        remote_notification = _parse_remote_html(remote, "notification.html")
        result = {
            "update_available": local_fp != remote_fp,
            "local_version": local_fp[:12],
            "latest_version": remote_fp[:12],
            "files": {"local": len(local), "remote": len(remote)},
            "changelog": changelog_diff,
            "has_changelog": bool(changelog_diff),
            "update_banner": remote_update_banner,
            "has_update_banner": bool(remote_update_banner),
            "notification": remote_notification,
            "has_notification": bool(remote_notification),
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
    base_dir = APP_DIR
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
    if sys.platform == "win32":
        flags = getattr(subprocess, "CREATE_NEW_CONSOLE", 0)
        if ext == ".ps1":
            subprocess.Popen(
                ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", script_path],
                cwd=script_dir,
                creationflags=flags,
            )
        elif ext in (".bat", ".cmd"):
            subprocess.Popen(
                ["cmd.exe", "/c", script_path],
                cwd=script_dir,
                creationflags=flags,
            )
        else:
            subprocess.Popen([script_path], cwd=script_dir, creationflags=flags)
    else:
        if ext == ".sh":
            try:
                os.chmod(script_path, 0o755)
            except Exception:
                pass
            subprocess.Popen(["bash", script_path], cwd=script_dir, start_new_session=True)
        elif ext == ".ps1":
            subprocess.Popen(
                ["pwsh", "-NoProfile", "-File", script_path],
                cwd=script_dir,
                start_new_session=True,
            )
        else:
            subprocess.Popen([script_path], cwd=script_dir, start_new_session=True)

def _dump_yaml_simple(data: Dict[str, Any]) -> str:
    def format_scalar(v: Any) -> str:
        if v is None:
            return ""
        if isinstance(v, bool):
            return "true" if v else "false"
        if isinstance(v, (int, float)):
            return str(v)
        v_str = str(v)
        if not v_str:
            return '""'
        needs_quotes = (
            v_str.lower() in ("true", "false", "yes", "no", "on", "off", "null", "none", "~")
            or any(c in v_str for c in (":", "#", "{", "}", "[", "]", ",", "&", "*", "?", "|", "-", "<", ">", "=", "!", "%", "@", "`", '"', "'", "\n", "\r", "\t"))
            or v_str.startswith((" ", "\t"))
            or v_str.endswith((" ", "\t"))
            or v_str.isdigit()
        )
        if needs_quotes:
            escaped = (
                v_str.replace("\\", "\\\\")
                .replace('"', '\\"')
                .replace("\n", "\\n")
                .replace("\r", "\\r")
                .replace("\t", "\\t")
            )
            return f'"{escaped}"'
        return v_str

    lines = ["# Auto-generated setup backup"]
    for section, values in data.items():
        if isinstance(values, dict):
            if not values:
                continue
            lines.append(f"{section}:")
            for k, v in values.items():
                formatted = format_scalar(v)
                if formatted:
                    lines.append(f"  {k}: {formatted}")
                else:
                    lines.append(f"  {k}:")
        else:
            formatted = format_scalar(values)
            if formatted:
                lines.append(f"{section}: {formatted}")
            else:
                lines.append(f"{section}:")
    return "\n".join(lines) + "\n"

def _parse_yaml_scalar(val_str: str) -> Any:
    val_str = val_str.strip()
    if not val_str:
        return ""
    if len(val_str) >= 2 and val_str.startswith('"') and val_str.endswith('"'):
        inner = val_str[1:-1]
        result = []
        i = 0
        n = len(inner)
        while i < n:
            if inner[i] == "\\" and i + 1 < n:
                c = inner[i + 1]
                if c == "n":
                    result.append("\n")
                elif c == "r":
                    result.append("\r")
                elif c == "t":
                    result.append("\t")
                elif c == '"':
                    result.append('"')
                elif c == "\\":
                    result.append("\\")
                else:
                    result.append(c)
                i += 2
            else:
                result.append(inner[i])
                i += 1
        return "".join(result)
    if len(val_str) >= 2 and val_str.startswith("'") and val_str.endswith("'"):
        inner = val_str[1:-1]
        return inner.replace("''", "'")
    if " #" in val_str:
        val_str = val_str.split(" #", 1)[0].strip()
    lower = val_str.lower()
    if lower in ("true", "yes", "on"):
        return True
    if lower in ("false", "no", "off"):
        return False
    if lower in ("null", "none", "~"):
        return None
    try:
        return int(val_str)
    except ValueError:
        pass
    try:
        return float(val_str)
    except ValueError:
        pass
    return val_str

def _load_yaml_simple(text: str) -> Dict[str, Any]:
    result: Dict[str, Any] = {}
    current_section: Optional[str] = None
    lines = text.splitlines()
    i = 0
    num_lines = len(lines)

    while i < num_lines:
        raw_line = lines[i]
        line = raw_line.rstrip()
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            i += 1
            continue

        indent = len(line) - len(line.lstrip())
        if ":" not in stripped:
            i += 1
            continue

        key_part, _, val_part = stripped.partition(":")
        key = key_part.strip()
        val_raw = val_part.strip()

        if (val_raw.startswith("'") and (len(val_raw) == 1 or not val_raw.endswith("'"))) or \
           (val_raw.startswith('"') and (len(val_raw) == 1 or not val_raw.endswith('"'))):
            quote_char = val_raw[0]
            multiline_parts = [val_raw]
            i += 1
            while i < num_lines:
                next_raw = lines[i]
                next_stripped = next_raw.strip()
                multiline_parts.append(next_raw)
                if next_stripped.endswith(quote_char):
                    break
                i += 1
            full_str = "\n".join(multiline_parts).strip()
            val = _parse_yaml_scalar(full_str)
            if indent == 0:
                result[key] = val
                current_section = None
            else:
                if current_section is not None:
                    if not isinstance(result.get(current_section), dict):
                        result[current_section] = {}
                    result[current_section][key] = val
                else:
                    result[key] = val
            i += 1
            continue

        if val_raw in ("|", "|-", "|+", ">", ">-", ">+"):
            block_lines = []
            i += 1
            while i < num_lines:
                next_raw = lines[i]
                next_line = next_raw.rstrip()
                if not next_line.strip():
                    block_lines.append("")
                    i += 1
                    continue
                next_indent = len(next_line) - len(next_line.lstrip())
                if next_indent <= indent:
                    break
                block_lines.append(next_line.lstrip())
                i += 1
            block_content = "\n".join(block_lines)
            if indent == 0:
                result[key] = block_content
                current_section = None
            else:
                if current_section is not None:
                    if not isinstance(result.get(current_section), dict):
                        result[current_section] = {}
                    result[current_section][key] = block_content
                else:
                    result[key] = block_content
            continue

        if indent == 0:
            if not val_raw or val_raw.startswith("#"):
                current_section = key
                if current_section not in result:
                    result[current_section] = {}
            else:
                current_section = None
                result[key] = _parse_yaml_scalar(val_raw)
        else:
            val = _parse_yaml_scalar(val_raw)
            if current_section is not None:
                if not isinstance(result.get(current_section), dict):
                    result[current_section] = {}
                result[current_section][key] = val
            else:
                result[key] = val
        i += 1

    return result

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

    try:
        with open(BACKUP_FILE, "r", encoding="utf-8") as f:
            content = f.read()
        loaded = _load_yaml_simple(content)
        data = _flatten_loaded_config(loaded or {})
        if not data:
            return {}
        return _strip_sensitive_values(data)
    except Exception as e:
        log_event(f"[ERROR] Failed to load setup_backup.yml: {e}", "error")
        return {}

def save_backup_config(data: Dict[str, Any]) -> bool:
    try:
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
                "freedom_xui_version", "freedom_decoy_template"
            ),
            "proxy_node": pick(
                "proxy_host", "proxy_host_for_ssh", "proxy_port", "proxy_user", "proxy_password", "proxy_key",
                "proxy_auth_type", "proxy_xui_username", "proxy_xui_password",
                "proxy_sub_secret", "proxy_client_tcp_list", "proxy_client_xhttp_list",
                "foreign_sub_url", "proxy_xui_version", "proxy_decoy_template"
            ),
            "standard_node": pick("vps_host", "vps_port", "vps_user", "vps_password", "vps_key", "vps_auth_type"),
            "sub_server": pick(
                "sub_vps_host", "sub_vps_port", "sub_vps_user", "sub_vps_password",
                "sub_vps_key", "sub_auth_type", "sub_domain", "sub_secret_path",
                "sub_russian_url", "sub_foreign_url", "sub_proxy_clients",
                "sub_freedom_clients", "sub_admin_user", "sub_backup_name",
                "rollback_sub_backup_file", "sub_decoy_template", "update_sub_decoy_template"
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
                "client_xhttp_list", "foreign_sub_url", "xui_version",
                "decoy_template", "freedom_decoy_template", "proxy_decoy_template", "sub_decoy_template"
            ),
            "update_node": pick(
                "update_vps_host", "update_vps_port", "update_vps_user",
                "update_vps_password", "update_vps_key", "update_auth_type",
                "update_xui_version", "update_decoy_template"
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

        content = _dump_yaml_simple(payload)
        with open(BACKUP_FILE, "w", encoding="utf-8") as f:
            f.write(content)

        return True
    except Exception as e:
        log_event(f"[ERROR] Failed to save setup_backup.yml: {e}", "error")
        return False

def list_backup_files(folder: str = "backups_panel") -> List[Dict[str, Any]]:
    backups_dir = os.path.join(APP_DIR, folder)
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
                self.send_json({"versions": ["latest"], "error": str(e)})
            return

        if url_path == "/api/decoys":
            try:
                self.send_json({"ok": True, "decoys": decoy_manager.get_decoy_catalog()})
            except Exception as e:
                self.send_json({"ok": False, "error": str(e), "decoys": []}, 500)
            return

        if url_path.startswith("/api/decoys/preview/"):
            parts = url_path[len("/api/decoys/preview/"):].split("/", 1)
            decoy_id = parts[0]
            sub_file = parts[1] if len(parts) > 1 and parts[1] else "index.html"
            try:
                decoy_dir = decoy_manager.ensure_decoy_cached(decoy_id)
                target_file = os.path.abspath(os.path.join(decoy_dir, sub_file))
                if not (target_file == decoy_dir or target_file.startswith(decoy_dir + os.sep)) or not os.path.isfile(target_file):
                    self.send_response(404)
                    self.end_headers()
                    self.wfile.write(b"404 Not Found")
                    return
                mime_type, _ = mimetypes.guess_type(target_file)
                mime_type = mime_type or "application/octet-stream"
                with open(target_file, "rb") as f:
                    content = f.read()
                self.send_response(200)
                self.send_header("Content-Type", mime_type)
                self.send_header("Content-Length", str(len(content)))
                self.end_headers()
                self.wfile.write(content)
            except Exception as e:
                self.send_response(500)
                self.end_headers()
                self.wfile.write(f"Preview error: {e}".encode("utf-8"))
            return

        if url_path == "/api/update_check":
            params = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            force = "force" in params or "1" in params.get("force", [])
            self.send_json(check_for_update(force=force))
            return

        if url_path == "/api/changelog":
            params = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            force = "force" in params or "1" in params.get("force", [])
            info = check_for_update(force=force)
            self.send_json({"ok": True, "changelog": info.get("changelog", ""), "update_available": info.get("update_available", False)})
            return

        if url_path == "/api/happ_routing":
            happ_file = os.path.join(APP_DIR, "panel", "templates", "3x-ui", "happ-routing.json")
            if os.path.exists(happ_file):
                try:
                    with open(happ_file, "r", encoding="utf-8") as f:
                        content = f.read()
                    self.send_json({"ok": True, "content": content})
                except Exception as e:
                    self.send_json({"ok": False, "error": str(e)}, 500)
            else:
                self.send_json({"ok": False, "error": "happ-routing.json not found"}, 404)
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
                    "app": "3x-ui-bootstrup",
                    "pid": os.getpid(),
                    "app_dir": APP_DIR,
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
            base_dir = os.path.join(APP_DIR, "resources")
            target_file = os.path.abspath(os.path.join(base_dir, url_path[len("/resources/"):].lstrip("/")))
        else:
            base_dir = os.path.join(APP_DIR, "panel", "static")
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

        if url_path == "/api/decoys/download":
            decoy_id = payload.get("id", "builtin")
            custom_url = payload.get("custom_url", "")
            try:
                path = decoy_manager.ensure_decoy_cached(decoy_id, custom_url=custom_url, force=True)
                self.send_json({"ok": True, "id": decoy_id, "cached": True, "path": path})
            except Exception as e:
                self.send_json({"ok": False, "error": str(e)}, 500)
            return

        if url_path == "/api/happ_routing":
            happ_file = os.path.join(APP_DIR, "panel", "templates", "3x-ui", "happ-routing.json")
            try:
                content = payload.get("content", "")
                if not content:
                    self.send_json({"ok": False, "error": "Content is required"}, 400)
                    return
                parsed = json.loads(content)
                formatted = json.dumps(parsed, indent=4, ensure_ascii=False)
                os.makedirs(os.path.dirname(happ_file), exist_ok=True)
                with open(happ_file, "w", encoding="utf-8") as f:
                    f.write(formatted + "\n")
                self.send_json({"ok": True, "content": formatted})
            except json.JSONDecodeError as jde:
                self.send_json({"ok": False, "error": f"Ошибка JSON: {str(jde)}"}, 400)
            except Exception as e:
                self.send_json({"ok": False, "error": str(e)}, 500)
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
            if not password and not key_data:
                self.send_json({"ok": False, "message": "SSH password or private key is required"}, 400)
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
            valid, err_msg = validate_deployment_config(payload)
            if not valid:
                self.send_json({"ok": False, "message": err_msg}, 400)
                return

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

            server_ref = self.server

            def run_update_bg():
                time.sleep(0.3)
                try:
                    server_ref.shutdown()
                    server_ref.server_close()
                except Exception:
                    pass
                time.sleep(0.2)
                try:
                    script_path = cli_script_path("update_sources")
                    if script_path:
                        launch_script(script_path)
                except Exception as e:
                    print(f"[ERROR] Failed to launch update script: {e}", file=sys.stderr)
                os._exit(0)

            t = threading.Thread(target=run_update_bg, daemon=False)
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
                    server_ref.shutdown()
                    server_ref.server_close()
                except Exception:
                    pass
                time.sleep(0.2)
                try:
                    script_path = cli_script_path("start_3x_ui_deployment_manager")
                    if script_path:
                        launch_script(script_path)
                    else:
                        main_py_path = os.path.join(APP_DIR, "main.py")
                        if sys.platform == "win32":
                            flags = getattr(subprocess, "CREATE_NEW_CONSOLE", 0)
                            subprocess.Popen([sys.executable, main_py_path], cwd=APP_DIR, creationflags=flags)
                        else:
                            subprocess.Popen([sys.executable, main_py_path], cwd=APP_DIR, start_new_session=True)
                except Exception as e:
                    print(f"[ERROR] Failed to restart server: {e}", file=sys.stderr)
                os._exit(0)

            t = threading.Thread(target=run_restart_bg, daemon=False)
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
                    server_ref.shutdown()
                    server_ref.server_close()
                except Exception:
                    pass
                time.sleep(0.2)
                os._exit(0)

            t = threading.Thread(target=run_shutdown_bg, daemon=False)
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
    block_on_close = False


def is_port_in_use(port: int, host: str = "127.0.0.1") -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            s.bind((host, port))
            return False
        except OSError:
            return True


def find_pids_on_port(port: int, host: str = "127.0.0.1") -> List[int]:
    pids = set()
    current_pid = os.getpid()

    # 1. Try lsof (Linux / macOS)
    try:
        res = subprocess.run(
            ["lsof", "-ti", f":{port}", "-sTCP:LISTEN"],
            capture_output=True, text=True, timeout=1.5
        )
        if res.returncode == 0 and res.stdout.strip():
            for line in res.stdout.strip().split():
                if line.isdigit():
                    pid = int(line)
                    if pid != current_pid and pid > 0:
                        pids.add(pid)
    except Exception:
        pass

    # 2. Try ss (Linux)
    if not pids and sys.platform.startswith("linux"):
        try:
            res = subprocess.run(
                ["ss", "-lptn", f"sport = :{port}"],
                capture_output=True, text=True, timeout=1.5
            )
            if res.returncode == 0 and res.stdout:
                for match in re.finditer(r"pid=(\d+)", res.stdout):
                    pid = int(match.group(1))
                    if pid != current_pid and pid > 0:
                        pids.add(pid)
        except Exception:
            pass

    # 3. Try fuser (Linux)
    if not pids and sys.platform.startswith("linux"):
        try:
            res = subprocess.run(
                ["fuser", f"{port}/tcp"],
                capture_output=True, text=True, timeout=1.5
            )
            if res.stdout:
                for token in res.stdout.strip().split():
                    if token.isdigit():
                        pid = int(token)
                        if pid != current_pid and pid > 0:
                            pids.add(pid)
        except Exception:
            pass

    # 4. Windows netstat
    if not pids and sys.platform == "win32":
        try:
            res = subprocess.run(
                ["netstat", "-ano", "-p", "tcp"],
                capture_output=True, text=True, timeout=2.0
            )
            if res.returncode == 0 and res.stdout:
                pattern = rf":{port}\s+.*LISTENING\s+(\d+)"
                for match in re.finditer(pattern, res.stdout, re.IGNORECASE):
                    pid = int(match.group(1))
                    if pid != current_pid and pid > 0:
                        pids.add(pid)
        except Exception:
            pass

    return sorted(list(pids))


def is_our_process(pid: int) -> bool:
    if pid <= 0 or pid == os.getpid():
        return False

    # Linux /proc inspection
    if sys.platform.startswith("linux"):
        cmdline_file = f"/proc/{pid}/cmdline"
        cwd_file = f"/proc/{pid}/cwd"
        if os.path.exists(cmdline_file):
            try:
                with open(cmdline_file, "rb") as f:
                    cmdline = f.read().decode("utf-8", errors="ignore").replace("\x00", " ")
                cwd = ""
                if os.path.exists(cwd_file):
                    try:
                        cwd = os.readlink(cwd_file)
                    except Exception:
                        pass

                if "main.py" in cmdline:
                    if (
                        APP_DIR in cmdline
                        or (cwd and APP_DIR in cwd)
                        or "3x-ui-bootstRUp" in cmdline
                        or "3x-ui-bootstRUp" in cwd
                        or "3x-ui" in cmdline
                        or "3xui" in cmdline
                    ):
                        return True
            except Exception:
                pass

    # Generic ps inspection (Linux / macOS)
    if sys.platform != "win32":
        try:
            res = subprocess.run(
                ["ps", "-p", str(pid), "-o", "args="],
                capture_output=True, text=True, timeout=1.5
            )
            if res.returncode == 0 and res.stdout:
                cmd = res.stdout
                if "main.py" in cmd and ("3x-ui" in cmd or "3xui" in cmd or "bootstRUp" in cmd or APP_DIR in cmd):
                    return True
        except Exception:
            pass

    # Windows wmic & PowerShell inspection
    if sys.platform == "win32":
        try:
            res = subprocess.run(
                ["wmic", "process", "where", f"processid={pid}", "get", "commandline"],
                capture_output=True, text=True, timeout=2.0
            )
            if res.returncode == 0 and res.stdout:
                cmd = res.stdout
                if "main.py" in cmd and ("3x-ui" in cmd or "3xui" in cmd or "bootstRUp" in cmd or APP_DIR in cmd):
                    return True
        except Exception:
            pass
        try:
            res = subprocess.run(
                ["powershell", "-NoProfile", "-Command", f"(Get-CimInstance Win32_Process -Filter 'ProcessId = {pid}').CommandLine"],
                capture_output=True, text=True, timeout=2.0
            )
            if res.returncode == 0 and res.stdout:
                cmd = res.stdout
                if "main.py" in cmd and ("3x-ui" in cmd or "3xui" in cmd or "bootstRUp" in cmd or APP_DIR in cmd):
                    return True
        except Exception:
            pass

    return False


def is_our_http_server(port: int, host: str = "127.0.0.1") -> Tuple[bool, Optional[int]]:
    url_status = f"http://{host}:{port}/api/status"
    try:
        req = urllib.request.Request(url_status, headers={"User-Agent": "3x-ui-bootstrUp-probe"})
        with urllib.request.urlopen(req, timeout=0.8) as resp:
            if resp.status == 200:
                body = resp.read().decode("utf-8", errors="ignore")
                data = json.loads(body)
                if isinstance(data, dict):
                    if data.get("app") == "3x-ui-bootstrup":
                        return True, data.get("pid")
                    if "deploying" in data and "status" in data and "logs_count" in data:
                        return True, data.get("pid")
    except Exception:
        pass

    url_root = f"http://{host}:{port}/"
    try:
        req = urllib.request.Request(url_root, headers={"User-Agent": "3x-ui-bootstrUp-probe"})
        with urllib.request.urlopen(req, timeout=0.8) as resp:
            if resp.status == 200:
                body = resp.read().decode("utf-8", errors="ignore")
                if "3X UI Deployment Manager" in body or "3x-ui-bootstRUp" in body:
                    return True, None
    except Exception:
        pass

    return False, None


def terminate_process(pid: Optional[int], port: Optional[int] = None, host: str = "127.0.0.1") -> None:
    if port is not None:
        try:
            req = urllib.request.Request(
                f"http://{host}:{port}/api/shutdown",
                data=b"{}",
                headers={"Content-Type": "application/json", "User-Agent": "3x-ui-bootstrUp-probe"},
                method="POST"
            )
            with urllib.request.urlopen(req, timeout=0.8) as resp:
                pass
        except Exception:
            pass

    if pid and pid > 0 and pid != os.getpid():
        if sys.platform == "win32":
            subprocess.run(["taskkill", "/F", "/PID", str(pid)], capture_output=True)
        else:
            try:
                os.kill(pid, signal.SIGTERM)
            except ProcessLookupError:
                return
            except Exception:
                pass

            for _ in range(20):
                time.sleep(0.1)
                try:
                    os.kill(pid, 0)
                except OSError:
                    return

            try:
                os.kill(pid, signal.SIGKILL)
            except OSError:
                pass


def bind_server(start_port: int = 8000, host: str = "127.0.0.1", max_attempts: int = 100) -> Tuple[ThreadingHTTPServer, int]:
    global PORT
    for offset in range(max_attempts):
        port = start_port + offset
        server_address = (host, port)
        try:
            httpd = ThreadingHTTPServer(server_address, WebUIHandler)
            PORT = port
            return httpd, port
        except OSError as e:
            if e.errno not in (48, 98, 10048) and "address already in use" not in str(e).lower():
                raise

            pids = find_pids_on_port(port, host)
            our_pids = [p for p in pids if is_our_process(p)]
            is_http_our, http_pid = is_our_http_server(port, host)
            if http_pid and http_pid not in our_pids and http_pid != os.getpid():
                our_pids.append(http_pid)

            if our_pids or is_http_our:
                target_pids = our_pids if our_pids else [None]
                pid_info = ", ".join(str(p) for p in our_pids) if our_pids else "HTTP detected"
                print(f"[!] Port {port} is occupied by an existing 3X UI Deployment Manager instance (PID: {pid_info}). Stopping old instance...")
                for p in target_pids:
                    terminate_process(p, port=port, host=host)

                time.sleep(0.3)
                try:
                    httpd = ThreadingHTTPServer(server_address, WebUIHandler)
                    print(f"[OK] Replaced old instance on port {port}.")
                    PORT = port
                    return httpd, port
                except OSError:
                    print(f"[!] Could not bind to port {port} after stopping old instance. Trying next port...")
                    continue
            else:
                proc_info = f"PID: {pids[0]}" if pids else "another process"
                print(f"[!] Port {port} is occupied by {proc_info}. Trying port {port + 1}...")
                continue

    raise RuntimeError(f"Could not bind to any port in range {start_port}..{start_port + max_attempts - 1}")


def main():
    httpd, port = bind_server(start_port=PORT, host=HOST)
    url = f"http://{HOST}:{port}"

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
        httpd.serve_forever(poll_interval=0.2)
    except (KeyboardInterrupt, SystemExit):
        print("\nShutting down server...")
    except OSError:
        pass
    finally:
        try:
            httpd.server_close()
        except Exception:
            pass

if __name__ == "__main__":
    main()
