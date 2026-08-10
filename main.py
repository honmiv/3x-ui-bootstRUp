import asyncio
import json
import mimetypes
import os
import sys
import urllib.parse
import webbrowser
from http.server import HTTPServer, BaseHTTPRequestHandler
from typing import Dict, Any, List

from ssh_deployer import SSHDeployer, run_deployment

PORT = 8000
HOST = "127.0.0.1"
BACKUP_FILE = os.path.join(os.path.dirname(__file__), "setup_backup.yml")

active_logs: List[Dict[str, str]] = []
is_deploying = False
deploy_status = "idle"
deploy_result: Dict[str, Any] = {}
cancel_requested = False

def is_cancel_requested() -> bool:
    global cancel_requested
    return cancel_requested

def log_event(message: str, level: str = "info"):
    global active_logs
    active_logs.append({"message": message, "level": level})

def load_backup_config() -> Dict[str, Any]:
    if not os.path.exists(BACKUP_FILE):
        return {}
    data = {}
    try:
        with open(BACKUP_FILE, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or ":" not in line:
                    continue
                k, v = line.split(":", 1)
                k = k.strip()
                v = v.strip().strip('"').strip("'")
                if not v:
                    continue
                if v.lower() == "true":
                    v = True
                elif v.lower() == "false":
                    v = False
                elif v.isdigit():
                    v = int(v)
                data[k] = v
    except Exception:
        pass
    return data

def save_backup_config(data: Dict[str, Any]):
    try:
        def fmt_val(v):
            if isinstance(v, bool):
                return "true" if v else "false"
            return f'"{v}"' if isinstance(v, str) else str(v)

        lines = ["# Auto-generated setup backup\n\n"]

        lines.append("common:\n")
        if "deploy_mode" in data:
            lines.append(f"  deploy_mode: {fmt_val(data['deploy_mode'])}\n")
        if "is_cascade" in data:
            lines.append(f"  is_cascade: {fmt_val(data['is_cascade'])}\n")
        lines.append("\n")

        lines.append("freedom_node:\n")
        for k in ["freedom_host", "freedom_port", "freedom_user", "freedom_password", "freedom_key", "freedom_auth_type", "freedom_xui_username", "freedom_xui_password", "freedom_sub_secret", "freedom_client_name", "freedom_xui_version"]:
            if k in data:
                lines.append(f"  {k}: {fmt_val(data[k])}\n")
        lines.append("\n")

        lines.append("proxy_node:\n")
        for k in ["proxy_host", "proxy_port", "proxy_user", "proxy_password", "proxy_key", "proxy_auth_type", "proxy_xui_username", "proxy_xui_password", "proxy_sub_secret", "proxy_client_tcp_list", "proxy_client_xhttp_list", "proxy_xui_version"]:
            if k in data:
                lines.append(f"  {k}: {fmt_val(data[k])}\n")
        lines.append("\n")

        lines.append("standard_node:\n")
        for k in ["vps_host", "vps_port", "vps_user", "vps_password", "vps_key", "vps_auth_type"]:
            if k in data:
                lines.append(f"  {k}: {fmt_val(data[k])}\n")
        lines.append("\n")

        lines.append("sub_server:\n")
        for k in ["sub_vps_host", "sub_vps_port", "sub_vps_user", "sub_vps_password", "sub_vps_key", "sub_auth_type", "sub_domain", "sub_secret_path", "sub_russian_url", "sub_foreign_url", "sub_proxy_clients", "sub_freedom_clients"]:
            if k in data:
                lines.append(f"  {k}: {fmt_val(data[k])}\n")
        lines.append("\n")

        lines.append("panel_and_clients:\n")
        for k in ["xui_username", "xui_password", "sub_secret", "client_tcp_list", "client_xhttp_list", "xui_version"]:
            if k in data:
                lines.append(f"  {k}: {fmt_val(data[k])}\n")
        lines.append("\n")

        lines.append("update_node:\n")
        for k in ["update_vps_host", "update_vps_port", "update_vps_user", "update_vps_password", "update_vps_key", "update_auth_type", "update_xui_version"]:
            if k in data:
                lines.append(f"  {k}: {fmt_val(data[k])}\n")
        lines.append("\n")

        with open(BACKUP_FILE, "w", encoding="utf-8") as f:
            f.writelines(lines)
    except Exception:
        pass

def list_backup_files() -> List[Dict[str, Any]]:
    backups_dir = os.path.join(os.path.dirname(__file__), "backups")
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

        if url_path == "/api/backups":
            self.send_json(list_backup_files())
            return

        if url_path == "/api/status":
            self.send_json({
                "deploying": is_deploying,
                "status": deploy_status,
                "logs_count": len(active_logs),
                "result": deploy_result
            })
            return

        if url_path == "/api/deploy/logs":
            self.send_response(200)
            self.send_header('Content-Type', 'text/event-stream')
            self.send_header('Cache-Control', 'no-cache')
            self.send_header('Connection', 'keep-alive')
            self.end_headers()

            sent_index = 0
            while True:
                if sent_index < len(active_logs):
                    item = active_logs[sent_index]
                    event_data = f"data: {json.dumps(item, ensure_ascii=False)}\n\n"
                    try:
                        self.wfile.write(event_data.encode('utf-8'))
                        self.wfile.flush()
                        sent_index += 1
                    except Exception:
                        break
                else:
                    if not is_deploying and sent_index >= len(active_logs):
                        done_item = {
                            "message": "[DONE] Installation process completed.",
                            "level": "success",
                            "event": "done",
                            "status": deploy_status
                        }
                        event_data = f"data: {json.dumps(done_item, ensure_ascii=False)}\n\n"
                        try:
                            self.wfile.write(event_data.encode('utf-8'))
                            self.wfile.flush()
                        except Exception:
                            pass
                        break
                    try:
                        import time
                        time.sleep(0.5)
                    except Exception:
                        break
            return

        if url_path == "/":
            url_path = "/index.html"

        static_dir = os.path.join(os.path.dirname(__file__), "static")
        target_file = os.path.abspath(os.path.join(static_dir, url_path.lstrip("/")))

        if not target_file.startswith(static_dir) or not os.path.isfile(target_file):
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
        except Exception:
            payload = {}

        if url_path == "/api/config":
            save_backup_config(payload)
            self.send_json({"ok": True})
            return

        if url_path == "/api/ssh/test":
            host = (payload.get("vps_host") or payload.get("backup_vps_host") or payload.get("recovery_vps_host") or payload.get("update_vps_host") or "").strip()
            port = int(payload.get("vps_port") or payload.get("backup_vps_port") or payload.get("recovery_vps_port") or payload.get("update_vps_port") or 22)
            user = (payload.get("vps_user") or payload.get("backup_vps_user") or payload.get("recovery_vps_user") or payload.get("update_vps_user") or "root").strip()
            password = payload.get("vps_password") if payload.get("vps_password") is not None else (payload.get("backup_vps_password") if payload.get("backup_vps_password") is not None else (payload.get("recovery_vps_password") if payload.get("recovery_vps_password") is not None else payload.get("update_vps_password", "")))
            key_data = payload.get("vps_key") if payload.get("vps_key") is not None else (payload.get("backup_vps_key") if payload.get("backup_vps_key") is not None else (payload.get("recovery_vps_key") if payload.get("recovery_vps_key") is not None else payload.get("update_vps_key", "")))

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
                loop.close()
                self.send_json({"ok": ok, "message": msg})
            except Exception as e:
                self.send_json({"ok": False, "message": f"Test exception: {str(e)}"})
            return

        if url_path == "/api/deploy/stop":
            if is_deploying:
                cancel_requested = True
                deploy_status = "cancelled"
                log_event("[CANCEL] Отмена процесса затребована пользователем...", "warning")
                self.send_json({"ok": True, "message": "Deployment cancellation requested"})
            else:
                self.send_json({"ok": False, "message": "No deployment currently running"}, 400)
            return

        if url_path == "/api/deploy":
            if is_deploying:
                self.send_json({"ok": False, "message": "Deployment already in progress"}, 400)
                return

            save_backup_config(payload)

            cancel_requested = False
            active_logs = []
            deploy_result = {}
            is_deploying = True
            deploy_status = "running"

            def start_deploy_bg(cfg):
                global is_deploying, deploy_status, deploy_result, cancel_requested
                import importlib
                import ssh_deployer
                importlib.reload(ssh_deployer)
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                try:
                    success, res_data = loop.run_until_complete(ssh_deployer.run_deployment(cfg, log_event, cancel_check=is_cancel_requested))
                    if cancel_requested:
                        deploy_status = "cancelled"
                        deploy_result = {}
                    else:
                        deploy_status = "completed" if success else "failed"
                        deploy_result = res_data if success else {}
                except Exception as e:
                    log_event(f"Unhandled deploy exception: {str(e)}", "error")
                    deploy_status = "failed"
                finally:
                    is_deploying = False
                    loop.close()

            import threading
            t = threading.Thread(target=start_deploy_bg, args=(payload,), daemon=True)
            t.start()

            self.send_json({"ok": True, "message": "Deployment started"})
            return

        if url_path == "/api/update_sources":
            if is_deploying:
                self.send_json({"ok": False, "message": "Нельзя обновлять исходники во время развертывания"}, 400)
                return

            self.send_json({"ok": True, "message": "Запуск обновления исходников..."})

            def run_update_bg():
                import time
                import subprocess
                time.sleep(0.5)
                script_path = os.path.join(os.path.dirname(__file__), "update_sources.sh")
                if os.path.exists(script_path):
                    os.chmod(script_path, 0o755)
                    subprocess.Popen(["bash", script_path], cwd=os.path.dirname(__file__), start_new_session=True)
                time.sleep(0.5)
                os._exit(0)

            import threading
            t = threading.Thread(target=run_update_bg, daemon=True)
            t.start()
            return

        if url_path == "/api/restart":
            if is_deploying:
                self.send_json({"ok": False, "message": "Нельзя перезапустить сервер во время развертывания"}, 400)
                return

            self.send_json({"ok": True, "message": "Перезапуск сервера..."})

            server_ref = self.server

            def run_restart_bg():
                import time
                import subprocess
                time.sleep(0.3)
                try:
                    server_ref.socket.close()
                except Exception:
                    pass
                time.sleep(0.3)
                script_name = "install.bat" if sys.platform.startswith("win") else "install.sh"
                script_path = os.path.join(os.path.dirname(__file__), script_name)
                if os.path.exists(script_path):
                    if not sys.platform.startswith("win"):
                        os.chmod(script_path, 0o755)
                        subprocess.Popen(["bash", script_path], cwd=os.path.dirname(__file__), start_new_session=True)
                    else:
                        subprocess.Popen([script_path], cwd=os.path.dirname(__file__), start_new_session=True)
                os._exit(0)

            import threading
            t = threading.Thread(target=run_restart_bg, daemon=True)
            t.start()
            return

        if url_path == "/api/shutdown":
            if is_deploying:
                self.send_json({"ok": False, "message": "Нельзя выключить сервер во время развертывания"}, 400)
                return

            self.send_json({"ok": True, "message": "Выключение сервера..."})

            server_ref = self.server

            def run_shutdown_bg():
                import time
                time.sleep(0.3)
                try:
                    server_ref.socket.close()
                except Exception:
                    pass
                time.sleep(0.2)
                os._exit(0)

            import threading
            t = threading.Thread(target=run_shutdown_bg, daemon=True)
            t.start()
            return

        self.send_json({"error": "Endpoint not found"}, 404)

def main():
    server_address = (HOST, PORT)
    httpd = None
    for attempt in range(5):
        try:
            httpd = HTTPServer(server_address, WebUIHandler)
            break
        except OSError as e:
            if attempt < 4 and e.errno in (48, 98):
                import time
                time.sleep(0.5)
            else:
                raise

    url = f"http://{HOST}:{PORT}"

    print(f"==================================================")
    print(f"  3x-ui-bootstRUp Web UI running at: {url}")
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
