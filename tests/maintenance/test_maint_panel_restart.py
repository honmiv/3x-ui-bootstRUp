#!/usr/bin/env python3
"""
Test: Maintenance - Panel Container Restart (deploy_mode: restart_panel)
1. Deploys panel on vps-maint-panel
2. Records container start times for 3xui, caddy, nginx-decoy
3. Executes restart_panel mode
4. Verifies containers were restarted (new start timestamps)
5. Verifies 3x-ui panel remains accessible after restart
"""

import asyncio
import hashlib
import os
import subprocess
import sys
import time

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from ssh_deployer import run_deployment
from tests.helpers import (
    prepare_test_repo,
    check_inner_containers_running,
    ensure_test_containers_running,
    fetch_panel_html,
    log,
)

CONTAINER = "vps-maint-panel"
PORT = 2261
DOMAIN = "maint-panel.test"

SUB_SECRET = "maint_restart_secret"
ADMIN_USER = "admin"
ADMIN_PASS = "MaintRestartPassword123!"


def get_container_start_time(c_name: str) -> str:
    res = subprocess.run(
        ["docker", "exec", CONTAINER, "docker", "inspect", c_name, "--format", "{{.State.StartedAt}}"],
        capture_output=True, text=True
    )
    return res.stdout.strip()


async def test_panel_restart() -> bool:
    ensure_test_containers_running(CONTAINER)

    # -------------------------------------------------------------------------
    # Step 1: Initial deployment
    # -------------------------------------------------------------------------
    log("=== STEP 1: Deploying panel on vps-maint-panel ===", "info")
    init_config = {
        "deploy_mode": "freedom_only",
        "vps_host": "127.0.0.1",
        "vps_port": PORT,
        "vps_user": "root",
        "vps_password": "root",
        "vps_auth_type": "password",
        "domain": DOMAIN,
        "xui_username": ADMIN_USER,
        "xui_password": ADMIN_PASS,
        "xui_version": "3.6.0",
        "sub_secret": SUB_SECRET,
        "freedom_client_name": "client-restart-test",
        "client_tcp_list": "client-restart-test",
        "bundle_source_dir": prepare_test_repo("panel"),
    }

    ok, res = await run_deployment(init_config, log)
    if not ok:
        log("Initial panel deployment failed!", "error")
        return False

    if not check_inner_containers_running(CONTAINER, ["3xui", "caddy", "nginx-decoy"]):
        return False

    web_base_path = hashlib.md5(f"{SUB_SECRET}-panel".encode("utf-8")).hexdigest()[:16]
    panel_html = fetch_panel_html(CONTAINER, f"https://{DOMAIN}/{web_base_path}/")
    if "3X-UI" not in panel_html and "login" not in panel_html.lower() and "html" not in panel_html.lower():
        log("Panel is not serving valid HTML before restart!", "error")
        return False

    # -------------------------------------------------------------------------
    # Step 2: Record start times
    # -------------------------------------------------------------------------
    before_starts = {
        c: get_container_start_time(c)
        for c in ["3xui", "caddy", "nginx-decoy"]
    }
    log(f"Container start times before restart: {before_starts}", "info")
    time.sleep(1.5)

    # -------------------------------------------------------------------------
    # Step 3: Run restart_panel mode
    # -------------------------------------------------------------------------
    log("=== STEP 3: Running restart_panel mode ===", "info")
    restart_config = {
        "deploy_mode": "restart_panel",
        "vps_host": "127.0.0.1",
        "vps_port": PORT,
        "vps_user": "root",
        "vps_password": "root",
        "vps_auth_type": "password",
        "update_vps_host": "127.0.0.1",
        "update_vps_port": PORT,
        "update_vps_user": "root",
        "update_vps_password": "root",
    }

    ok_rst, res_rst = await run_deployment(restart_config, log)
    if not ok_rst:
        log("restart_panel deployment failed!", "error")
        return False

    if not check_inner_containers_running(CONTAINER, ["3xui", "caddy", "nginx-decoy"]):
        return False

    # -------------------------------------------------------------------------
    # Step 4: Verify start times changed
    # -------------------------------------------------------------------------
    after_starts = {
        c: get_container_start_time(c)
        for c in ["3xui", "caddy", "nginx-decoy"]
    }
    log(f"Container start times after restart: {after_starts}", "info")

    for c in ["3xui", "caddy", "nginx-decoy"]:
        if before_starts[c] == after_starts[c]:
            log(f"Container {c} did not change start time! ({before_starts[c]} == {after_starts[c]})", "error")
            return False
        log(f"Container {c} successfully restarted.", "success")

    # -------------------------------------------------------------------------
    # Step 5: Verify panel is accessible
    # -------------------------------------------------------------------------
    post_html = fetch_panel_html(CONTAINER, f"https://{DOMAIN}/{web_base_path}/")
    if "3X-UI" not in post_html and "login" not in post_html.lower() and "html" not in post_html.lower():
        log("Panel did not respond with valid HTML after restart!", "error")
        return False

    log("==================================================", "success")
    log("🎉 TEST PANEL RESTART PASSED! 🎉", "success")
    log("==================================================", "success")
    return True


def main():
    ok = asyncio.run(test_panel_restart())
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()

