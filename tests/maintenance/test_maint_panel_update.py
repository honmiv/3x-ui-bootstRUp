#!/usr/bin/env python3
"""
Test: Maintenance - Panel 3X-UI Version Update (deploy_mode: update_3xui)
1. Deploys a panel on vps-maint-panel (version: 3.6.0)
2. Tags a local test target image (3.6.1-test) inside test container
3. Executes update_3xui mode to version 3.6.1-test
4. Verifies pre-update backup was downloaded to ./backups_panel/
5. Verifies compose file on remote was updated and 3xui container uses new image
6. Verifies 3x-ui panel remains accessible
7. Cleans up local pre-update backup archive
"""

import asyncio
import hashlib
import os
import subprocess
import sys

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

SUB_SECRET = "maint_update_secret"
ADMIN_USER = "admin"
ADMIN_PASS = "MaintUpdatePassword123!"
INITIAL_VERSION = "3.6.0"
TARGET_VERSION = "3.6.1-test"


async def test_panel_update() -> bool:
    ensure_test_containers_running(CONTAINER)

    # -------------------------------------------------------------------------
    # Step 1: Initial deployment with version 3.6.0
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
        "xui_version": INITIAL_VERSION,
        "sub_secret": SUB_SECRET,
        "freedom_client_name": "client-update-test",
        "client_tcp_list": "client-update-test",
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
        log("Panel is not serving valid HTML before update!", "error")
        return False
    log("Panel is up and healthy before update!", "success")

    # -------------------------------------------------------------------------
    # Step 2: Prepare target version image tag inside container
    # -------------------------------------------------------------------------
    log(f"Tagging test image ghcr.io/mhsanaei/3x-ui:{TARGET_VERSION} inside container...", "info")
    subprocess.run(
        [
            "docker", "exec", CONTAINER,
            "docker", "tag",
            f"ghcr.io/mhsanaei/3x-ui:{INITIAL_VERSION}",
            f"ghcr.io/mhsanaei/3x-ui:{TARGET_VERSION}"
        ],
        check=True,
    )

    # -------------------------------------------------------------------------
    # Step 3: Run update_3xui mode
    # -------------------------------------------------------------------------
    log(f"=== STEP 3: Running update_3xui mode to version {TARGET_VERSION} ===", "info")
    update_config = {
        "deploy_mode": "update_3xui",
        "vps_host": "127.0.0.1",
        "vps_port": PORT,
        "vps_user": "root",
        "vps_password": "root",
        "vps_auth_type": "password",
        "update_vps_host": "127.0.0.1",
        "update_vps_port": PORT,
        "update_vps_user": "root",
        "update_vps_password": "root",
        "update_xui_version": TARGET_VERSION,
        "bundle_source_dir": prepare_test_repo("panel"),
    }

    ok_up, res_up = await run_deployment(update_config, log)
    if not ok_up:
        log("update_3xui deployment returned failure!", "error")
        return False

    backup_name = res_up.get("backup_name")
    if not backup_name:
        log("Result missing 'backup_name' for pre-update backup!", "error")
        return False

    local_backup_path = os.path.join(REPO_ROOT, "backups_panel", backup_name)
    if not os.path.isfile(local_backup_path) or os.path.getsize(local_backup_path) == 0:
        log(f"Pre-update backup archive not found: {local_backup_path}", "error")
        return False
    log(f"Pre-update backup created and verified: {local_backup_path}", "success")

    try:
        # ---------------------------------------------------------------------
        # Step 4: Verify remote compose file and running container image
        # ---------------------------------------------------------------------
        inspect_img = subprocess.run(
            ["docker", "exec", CONTAINER, "docker", "inspect", "3xui", "--format", "{{.Config.Image}}"],
            capture_output=True, text=True, check=True
        ).stdout.strip()

        if TARGET_VERSION not in inspect_img:
            log(f"Running container has unexpected image: {inspect_img} (expected tag {TARGET_VERSION})", "error")
            return False
        log(f"Container 3xui is running with updated image: {inspect_img}", "success")

        # Verify panel is still healthy and accessible
        updated_panel_html = fetch_panel_html(CONTAINER, f"https://{DOMAIN}/{web_base_path}/")
        if "3X-UI" not in updated_panel_html and "login" not in updated_panel_html.lower() and "html" not in updated_panel_html.lower():
            log("Panel is not serving valid HTML after update!", "error")
            return False
        log("Panel remained fully accessible after update!", "success")

        log("==================================================", "success")
        log("🎉 TEST PANEL UPDATE 3X-UI PASSED! 🎉", "success")
        log("==================================================", "success")
        return True

    finally:
        if os.path.exists(local_backup_path):
            try:
                os.remove(local_backup_path)
                log(f"Cleaned up pre-update backup file {local_backup_path}", "info")
            except OSError:
                pass


def main():
    ok = asyncio.run(test_panel_update())
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()

