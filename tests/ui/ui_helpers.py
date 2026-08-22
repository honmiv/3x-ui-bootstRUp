#!/usr/bin/env python3
"""
Shared helpers and fixture utilities for Playwright UI E2E tests.
Provides sandboxed execution for:
- Local Control Panel (main.py)
- Subscription Server (sub-server/server.py)
"""

import importlib.util
import json
import os
import shutil
import socket
import sys
import threading
from http.server import ThreadingHTTPServer

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

import main as backend_main
from tests.helpers import log


def get_free_port(preferred_port: int = 8090) -> int:
    """Finds an available local TCP port."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            s.bind(("127.0.0.1", preferred_port))
            return preferred_port
        except OSError:
            s.bind(("127.0.0.1", 0))
            return s.getsockname()[1]


def start_sandboxed_control_panel(sandbox_name: str = "cp_sandbox", preferred_port: int = 0):
    """Starts an isolated instance of main.py Local Control Panel on a race-free ephemeral port."""
    sandbox_dir = os.path.join(REPO_ROOT, "tests", ".cache", f"ui_{sandbox_name}")
    if os.path.exists(sandbox_dir):
        shutil.rmtree(sandbox_dir, ignore_errors=True)
    os.makedirs(sandbox_dir, exist_ok=True)

    servers_file = os.path.join(sandbox_dir, "servers.json")
    backup_file = os.path.join(sandbox_dir, "setup_backup.yml")

    # Set sandboxed file paths
    backend_main.SERVERS_FILE = servers_file
    backend_main.BACKUP_FILE = backup_file
    backend_main.active_logs.clear()
    backend_main.is_deploying = False
    backend_main.cancel_requested = False

    server = ThreadingHTTPServer(("127.0.0.1", 0), backend_main.WebUIHandler)
    port = server.server_address[1]
    server_url = f"http://127.0.0.1:{port}"

    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    return server, server_url, servers_file, backup_file, sandbox_dir


def start_sandboxed_sub_server(
    sandbox_name: str = "sub_sandbox",
    preferred_port: int = 0,
    initial_nodes: list = None,
    admin_user: str = "subadmin",
    admin_password: str = "SubAdminSecurePass123!",
    secret_path: str = "subs"
):
    """Starts an isolated instance of sub-server/server.py on a race-free ephemeral port."""
    sandbox_dir = os.path.join(REPO_ROOT, "tests", ".cache", f"ui_{sandbox_name}")
    if os.path.exists(sandbox_dir):
        shutil.rmtree(sandbox_dir, ignore_errors=True)
    os.makedirs(sandbox_dir, exist_ok=True)

    nodes_file = os.path.join(sandbox_dir, "nodes.json")
    force_file = os.path.join(sandbox_dir, "force-subs.yml")
    log_file = os.path.join(sandbox_dir, "sub-server.log")

    os.environ["NODES_FILE"] = nodes_file
    os.environ["FORCE_FILE"] = force_file
    os.environ["LOG_FILE"] = log_file
    os.environ["SECRET_SUB_PATH"] = secret_path
    os.environ["ADMIN_USER"] = admin_user
    os.environ["ADMIN_PASSWORD"] = admin_password

    if initial_nodes is not None:
        with open(nodes_file, "w", encoding="utf-8") as f:
            json.dump(initial_nodes, f, indent=2)

    spec = importlib.util.spec_from_file_location("sub_server_mod", os.path.join(REPO_ROOT, "sub-server", "server.py"))
    sub_mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(sub_mod)
    if os.path.exists(nodes_file):
        sub_mod.NODES = sub_mod.load_nodes(nodes_file)

    server = ThreadingHTTPServer(("127.0.0.1", 0), sub_mod.Handler)
    port = server.server_address[1]
    server_url = f"http://127.0.0.1:{port}"

    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    return server, server_url, nodes_file, force_file, sandbox_dir, sub_mod


async def mock_ssh_success(page):
    """Mocks POST /api/ssh/test returning { ok: true } to allow advancing."""
    await page.route("**/api/ssh/test", lambda route: route.fulfill(status=200, json={"ok": True, "message": "Connected"}))
