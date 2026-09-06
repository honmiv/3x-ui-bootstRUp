"""HTTP route handlers for the 3x-UI control panel (Phase D1 of REFACTORING.md).

Route dispatch extracted from main.py::WebUIHandler.do_GET/do_POST/do_DELETE.
Each handler is a standalone function; dispatch is a path -> handler table.

main.py imports this module lazily (inside do_GET/do_POST/do_DELETE) to avoid
the circular import; main is always fully loaded by then. All references to
main-module global state go through ``M.`` so runtime reassignment of module
attributes (tests, server lifecycle) is always visible.
"""

import asyncio
import json
import mimetypes
import os
import subprocess
import sys
import threading
import time
import urllib.parse

import main as M


def handle_get(handler):
    url_path = urllib.parse.urlparse(handler.path).path

    if url_path == "/api/config":
        handler.send_json(M.load_backup_config())
        return

    if url_path == "/api/xui_versions":
        try:
            handler.send_json({"versions": M.fetch_xui_versions()})
        except Exception as e:
            handler.send_json({"versions": ["latest"], "error": str(e)})
        return

    if url_path == "/api/decoys":
        try:
            handler.send_json({"ok": True, "decoys": M.decoy_manager.get_decoy_catalog()})
        except Exception as e:
            handler.send_json({"ok": False, "error": str(e), "decoys": []}, 500)
        return

    if url_path.startswith("/api/decoys/preview/"):
        _get_decoy_preview(handler, url_path)
        return

    if url_path == "/api/update_check":
        _get_update_check(handler)
        return

    if url_path == "/api/changelog":
        _get_changelog(handler)
        return

    if url_path == "/api/happ_routing":
        _get_happ_routing(handler)
        return

    if url_path == "/api/backups":
        _get_backups(handler)
        return

    if url_path == "/api/status":
        _get_status(handler)
        return

    if url_path == "/api/servers":
        _get_servers(handler)
        return

    if url_path == "/api/deploy/logs":
        _get_deploy_logs(handler)
        return

    if url_path == "/":
        url_path = "/index.html"

    _get_static(handler, url_path)


def _get_decoy_preview(handler, url_path):
    parts = url_path[len("/api/decoys/preview/"):].split("/", 1)
    decoy_id = parts[0]
    sub_file = parts[1] if len(parts) > 1 and parts[1] else "index.html"
    try:
        decoy_dir = M.decoy_manager.ensure_decoy_cached(decoy_id)
        target_file = os.path.abspath(os.path.join(decoy_dir, sub_file))
        if not (target_file == decoy_dir or target_file.startswith(decoy_dir + os.sep)) or not os.path.isfile(target_file):
            handler.send_response(404)
            handler.end_headers()
            handler.wfile.write(b"404 Not Found")
            return
        mime_type, _ = mimetypes.guess_type(target_file)
        mime_type = mime_type or "application/octet-stream"
        with open(target_file, "rb") as f:
            content = f.read()
        handler.send_response(200)
        handler.send_header("Content-Type", mime_type)
        handler.send_header("Content-Length", str(len(content)))
        handler.end_headers()
        handler.wfile.write(content)
    except Exception as e:
        handler.send_response(500)
        handler.end_headers()
        handler.wfile.write(f"Preview error: {e}".encode("utf-8"))


def _get_update_check(handler):
    params = urllib.parse.parse_qs(urllib.parse.urlparse(handler.path).query)
    force = "force" in params or "1" in params.get("force", [])
    handler.send_json(M.check_for_update(force=force))


def _get_changelog(handler):
    params = urllib.parse.parse_qs(urllib.parse.urlparse(handler.path).query)
    force = "force" in params or "1" in params.get("force", [])
    info = M.check_for_update(force=force)
    handler.send_json({"ok": True, "changelog": info.get("changelog", ""), "update_available": info.get("update_available", False)})


def _get_happ_routing(handler):
    happ_file = os.path.join(M.APP_DIR, "panel", "templates", "3x-ui", "happ-routing.json")
    if os.path.exists(happ_file):
        try:
            with open(happ_file, "r", encoding="utf-8") as f:
                content = f.read()
            handler.send_json({"ok": True, "content": content})
        except Exception as e:
            handler.send_json({"ok": False, "error": str(e)}, 500)
    else:
        handler.send_json({"ok": False, "error": "happ-routing.json not found"}, 404)


def _get_backups(handler):
    params = urllib.parse.parse_qs(urllib.parse.urlparse(handler.path).query)
    folder = params.get("folder", ["backups_panel"])[0]
    if folder == "backups_sub_server":
        handler.send_json(M.list_backup_files("backups_sub_server"))
    else:
        handler.send_json(M.list_backup_files("backups_panel"))


def _get_status(handler):
    with M.DEPLOY_LOCK:
        status_payload = {
            "app": "3x-ui-bootstrup",
            "pid": os.getpid(),
            "app_dir": M.APP_DIR,
            "deploying": M.is_deploying,
            "status": M.deploy_status,
            "logs_count": len(M.active_logs),
            "result": dict(M.deploy_result)
        }
    handler.send_json(status_payload)


def _get_servers(handler):
    if not os.path.exists(M.SERVERS_FILE):
        handler.send_json([])
        return
    try:
        with open(M.SERVERS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        handler.send_json(data)
    except Exception:
        handler.send_json([])


def _get_deploy_logs(handler):
    handler.send_response(200)
    handler.send_header('Content-Type', 'text/event-stream')
    handler.send_header('Cache-Control', 'no-cache')
    handler.send_header('Connection', 'keep-alive')
    handler.end_headers()

    sent_index = 0
    while True:
        with M.LOG_CONDITION:
            while M.is_deploying and sent_index >= len(M.active_logs):
                M.LOG_CONDITION.wait(timeout=1.0)

            new_items = list(M.active_logs[sent_index:])
            still_deploying = M.is_deploying
            final_status = M.deploy_status

        for item in new_items:
            event_data = f"data: {json.dumps(item, ensure_ascii=False)}\n\n"
            try:
                handler.wfile.write(event_data.encode('utf-8'))
                handler.wfile.flush()
                sent_index += 1
            except Exception:
                return

        if not still_deploying and sent_index >= len(M.active_logs):
            done_item = {
                "message": "[DONE] Installation process completed.",
                "level": "success",
                "event": "done",
                "status": final_status
            }
            event_data = f"data: {json.dumps(done_item, ensure_ascii=False)}\n\n"
            try:
                handler.wfile.write(event_data.encode('utf-8'))
                handler.wfile.flush()
            except Exception:
                pass
            break


def _get_static(handler, url_path):
    if url_path.startswith("/resources/"):
        base_dir = os.path.join(M.APP_DIR, "resources")
        target_file = os.path.abspath(os.path.join(base_dir, url_path[len("/resources/"):].lstrip("/")))
    else:
        base_dir = os.path.join(M.APP_DIR, "panel", "static")
        target_file = os.path.abspath(os.path.join(base_dir, url_path.lstrip("/")))

    if not (target_file == base_dir or target_file.startswith(base_dir + os.sep)) or not os.path.isfile(target_file):
        handler.send_response(404)
        handler.end_headers()
        handler.wfile.write(b"404 Not Found")
        return

    mime_type, _ = mimetypes.guess_type(target_file)
    if not mime_type:
        mime_type = "application/octet-stream"

    try:
        with open(target_file, "rb") as f:
            content = f.read()
        handler.send_response(200)
        handler.send_header("Content-Type", mime_type)
        handler.send_header("Content-Length", str(len(content)))
        handler.send_header("Cache-Control", "no-store, no-cache, must-revalidate, max-age=0")
        handler.send_header("Pragma", "no-cache")
        handler.send_header("Expires", "0")
        handler.end_headers()
        handler.wfile.write(content)
    except Exception as e:
        handler.send_response(500)
        handler.end_headers()
        handler.wfile.write(str(e).encode('utf-8'))


def handle_post(handler):
    url_path = urllib.parse.urlparse(handler.path).path
    content_len = int(handler.headers.get('Content-Length', 0))
    post_body = handler.rfile.read(content_len)

    try:
        payload = json.loads(post_body.decode('utf-8')) if post_body else {}
    except json.JSONDecodeError:
        handler.send_json({"error": "Invalid JSON"}, 400)
        return

    if url_path == "/api/servers":
        _post_servers(handler, payload)
        return

    if url_path == "/api/config":
        _post_config(handler, payload)
        return

    if url_path == "/api/decoys/download":
        _post_decoys_download(handler, payload)
        return

    if url_path == "/api/happ_routing":
        _post_happ_routing(handler, payload)
        return

    if url_path == "/api/ssh/test":
        _post_ssh_test(handler, payload)
        return

    if url_path == "/api/deploy/stop":
        _post_deploy_stop(handler)
        return

    if url_path == "/api/deploy":
        _post_deploy(handler, payload)
        return

    if url_path == "/api/update_sources":
        _post_update_sources(handler)
        return

    if url_path == "/api/restart":
        _post_restart(handler)
        return

    if url_path == "/api/shutdown":
        _post_shutdown(handler)
        return

    handler.send_json({"error": "Endpoint not found"}, 404)


def _post_servers(handler, payload):
    try:
        with open(M.SERVERS_FILE, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
        handler.send_json({"ok": True})
    except Exception as e:
        handler.send_json({"error": str(e)}, 500)


def _post_config(handler, payload):
    if M.save_backup_config(payload):
        handler.send_json({"ok": True})
    else:
        handler.send_json({"ok": False, "error": "Failed to save setup_backup.yml"}, 500)


def _post_decoys_download(handler, payload):
    decoy_id = payload.get("id", "builtin")
    custom_url = payload.get("custom_url", "")
    try:
        path = M.decoy_manager.ensure_decoy_cached(decoy_id, custom_url=custom_url, force=True)
        handler.send_json({"ok": True, "id": decoy_id, "cached": True, "path": path})
    except Exception as e:
        handler.send_json({"ok": False, "error": str(e)}, 500)


def _post_happ_routing(handler, payload):
    happ_file = os.path.join(M.APP_DIR, "panel", "templates", "3x-ui", "happ-routing.json")
    try:
        content = payload.get("content", "")
        if not content:
            handler.send_json({"ok": False, "error": "Content is required"}, 400)
            return
        parsed = json.loads(content)
        formatted = json.dumps(parsed, indent=4, ensure_ascii=False)
        os.makedirs(os.path.dirname(happ_file), exist_ok=True)
        with open(happ_file, "w", encoding="utf-8") as f:
            f.write(formatted + "\n")
        handler.send_json({"ok": True, "content": formatted})
    except json.JSONDecodeError as jde:
        handler.send_json({"ok": False, "error": f"Ошибка JSON: {str(jde)}"}, 400)
    except Exception as e:
        handler.send_json({"ok": False, "error": str(e)}, 500)


def _post_ssh_test(handler, payload):
    host = (payload.get("vps_host") or payload.get("backup_vps_host") or payload.get("recovery_vps_host") or payload.get("update_vps_host") or payload.get("sub_vps_host") or "").strip()
    port = int(payload.get("vps_port") or payload.get("backup_vps_port") or payload.get("recovery_vps_port") or payload.get("update_vps_port") or payload.get("sub_vps_port") or 22)
    user = (payload.get("vps_user") or payload.get("backup_vps_user") or payload.get("recovery_vps_user") or payload.get("update_vps_user") or payload.get("sub_vps_user") or "root").strip()
    password = payload.get("vps_password") if payload.get("vps_password") is not None else (payload.get("backup_vps_password") if payload.get("backup_vps_password") is not None else (payload.get("recovery_vps_password") if payload.get("recovery_vps_password") is not None else (payload.get("update_vps_password") if payload.get("update_vps_password") is not None else payload.get("sub_vps_password", ""))))
    key_data = payload.get("vps_key") if payload.get("vps_key") is not None else (payload.get("backup_vps_key") if payload.get("backup_vps_key") is not None else (payload.get("recovery_vps_key") if payload.get("recovery_vps_key") is not None else (payload.get("update_vps_key") if payload.get("update_vps_key") is not None else payload.get("sub_vps_key", ""))))

    if not host:
        handler.send_json({"ok": False, "message": "Host address is required"}, 400)
        return
    if not password and not key_data:
        handler.send_json({"ok": False, "message": "SSH password or private key is required"}, 400)
        return

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    async def run_test():
        async with M.SSHDeployer(host, port, user, password, key_data) as deployer:
            return await deployer.test_connection()

    try:
        ok, msg = loop.run_until_complete(run_test())
        handler.send_json({"ok": ok, "message": msg})
    except Exception as e:
        handler.send_json({"ok": False, "message": f"Test exception: {str(e)}"})
    finally:
        loop.close()


def _post_deploy_stop(handler):
    with M.DEPLOY_LOCK:
        if M.is_deploying:
            M.cancel_requested = True
            M.deploy_status = "cancelled"
            already_running = True
        else:
            already_running = False
    if already_running:
        M.log_event("[CANCEL] Отмена процесса затребована пользователем...", "warning")
        handler.send_json({"ok": True, "message": "Deployment cancellation requested"})
    else:
        handler.send_json({"ok": False, "message": "No deployment currently running"}, 400)


def _post_deploy(handler, payload):
    valid, err_msg = M.validate_deployment_config(payload)
    if not valid:
        handler.send_json({"ok": False, "message": err_msg}, 400)
        return

    with M.DEPLOY_LOCK:
        if M.is_deploying:
            handler.send_json({"ok": False, "message": "Deployment already in progress"}, 400)
            return

        M.cancel_requested = False
        M.active_logs.clear()
        M.deploy_result = {}
        M.is_deploying = True
        M.deploy_status = "running"
        M.LOG_CONDITION.notify_all()

    M.save_backup_config(payload)

    def start_deploy_bg(cfg):
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            success, res_data = loop.run_until_complete(M.run_deployment(cfg, M.log_event, cancel_check=M.is_cancel_requested))
            with M.LOG_CONDITION:
                if M.cancel_requested:
                    M.deploy_status = "cancelled"
                    M.deploy_result = {}
                else:
                    M.deploy_status = "completed" if success else "failed"
                    M.deploy_result = res_data if success else {}
        except Exception as e:
            M.log_event(f"Unhandled deploy exception: {str(e)}", "error")
            with M.LOG_CONDITION:
                M.deploy_status = "failed"
        finally:
            with M.LOG_CONDITION:
                M.is_deploying = False
                M.LOG_CONDITION.notify_all()
            loop.close()

    t = threading.Thread(target=start_deploy_bg, args=(payload,), daemon=True)
    t.start()

    handler.send_json({"ok": True, "message": "Deployment started"})


def _post_update_sources(handler):
    with M.DEPLOY_LOCK:
        if M.is_deploying:
            handler.send_json({"ok": False, "message": "Нельзя обновлять исходники во время развертывания"}, 400)
            return

    handler.send_json({"ok": True, "message": "Запуск обновления исходников..."})

    server_ref = handler.server

    def run_update_bg():
        time.sleep(0.3)
        try:
            server_ref.shutdown()
            server_ref.server_close()
        except Exception:
            pass
        time.sleep(0.2)
        try:
            script_path = M.cli_script_path("update_sources")
            if script_path:
                M.launch_script(script_path)
        except Exception as e:
            print(f"[ERROR] Failed to launch update script: {e}", file=sys.stderr)
        os._exit(0)

    t = threading.Thread(target=run_update_bg, daemon=False)
    t.start()


def _post_restart(handler):
    with M.DEPLOY_LOCK:
        if M.is_deploying:
            handler.send_json({"ok": False, "message": "Нельзя перезапустить сервер во время развертывания"}, 400)
            return

    handler.send_json({"ok": True, "message": "Перезапуск сервера..."})

    server_ref = handler.server

    def run_restart_bg():
        time.sleep(0.3)
        try:
            server_ref.shutdown()
            server_ref.server_close()
        except Exception:
            pass
        time.sleep(0.2)
        try:
            script_path = M.cli_script_path("start_3x_ui_deployment_manager")
            if script_path:
                M.launch_script(script_path)
            else:
                main_py_path = os.path.join(M.APP_DIR, "main.py")
                if sys.platform == "win32":
                    flags = getattr(subprocess, "CREATE_NEW_CONSOLE", 0)
                    subprocess.Popen([sys.executable, main_py_path], cwd=M.APP_DIR, creationflags=flags)
                else:
                    subprocess.Popen([sys.executable, main_py_path], cwd=M.APP_DIR, start_new_session=True)
        except Exception as e:
            print(f"[ERROR] Failed to restart server: {e}", file=sys.stderr)
        os._exit(0)

    t = threading.Thread(target=run_restart_bg, daemon=False)
    t.start()


def _post_shutdown(handler):
    with M.DEPLOY_LOCK:
        if M.is_deploying:
            handler.send_json({"ok": False, "message": "Нельзя выключить сервер во время развертывания"}, 400)
            return

    handler.send_json({"ok": True, "message": "Выключение сервера..."})

    server_ref = handler.server

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


def handle_delete(handler):
    url_path = urllib.parse.urlparse(handler.path).path
    if url_path == "/api/servers/reset":
        try:
            if os.path.exists(M.SERVERS_FILE):
                os.remove(M.SERVERS_FILE)
            handler.send_json({"ok": True})
        except Exception as e:
            handler.send_json({"error": str(e)}, 500)
        return

    handler.send_json({"error": "Endpoint not found"}, 404)