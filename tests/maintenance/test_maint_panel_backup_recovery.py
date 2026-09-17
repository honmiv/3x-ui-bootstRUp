#!/usr/bin/env python3
"""
Test: Maintenance - Panel Backup & Recovery (deploy_mode: backup, recovery)
1. Deploys a panel on vps-maint-panel (domain maint-panel.test)
2. Executes backup mode -> verifies local archive in ./backups_panel/
3. Executes recovery mode onto clean container vps-maint-recovery (domain maint-recovery.test)
4. Verifies domain rewrite, container startup, and 3x-ui panel access
5. Cleans up local backup archive
"""

import asyncio
import hashlib
import os
import sys
import tarfile

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

ORIGIN_CONTAINER = "vps-maint-panel"
ORIGIN_PORT = 2261
ORIGIN_DOMAIN = "maint-panel.test"

TARGET_CONTAINER = "vps-maint-recovery"
TARGET_PORT = 2262
TARGET_DOMAIN = "maint-recovery.test"

SUB_SECRET = "maint_secret_phrase"
ADMIN_USER = "admin"
ADMIN_PASS = "MaintAdminPassword123!"


async def test_panel_backup_and_recovery() -> bool:
    ensure_test_containers_running(ORIGIN_CONTAINER, TARGET_CONTAINER)

    # -------------------------------------------------------------------------
    # Step 1: Initial deployment on origin container
    # -------------------------------------------------------------------------
    log("=== STEP 1: Deploying initial panel on vps-maint-panel ===", "info")
    init_config = {
        "deploy_mode": "freedom_only",
        "vps_host": "127.0.0.1",
        "vps_port": ORIGIN_PORT,
        "vps_user": "root",
        "vps_password": "root",
        "vps_auth_type": "password",
        "domain": ORIGIN_DOMAIN,
        "xui_username": ADMIN_USER,
        "xui_password": ADMIN_PASS,
        "xui_version": "3.6.0",
        "sub_secret": SUB_SECRET,
        "freedom_client_name": "client-backup-test",
        "client_tcp_list": "client-backup-test",
        "bundle_source_dir": prepare_test_repo("panel"),
    }

    ok, res = await run_deployment(init_config, log)
    if not ok:
        log("Initial panel deployment failed!", "error")
        return False

    if not check_inner_containers_running(ORIGIN_CONTAINER, ["3xui", "caddy", "nginx-decoy"]):
        return False

    web_base_path = hashlib.md5(f"{SUB_SECRET}-panel".encode("utf-8")).hexdigest()[:16]
    panel_html = fetch_panel_html(ORIGIN_CONTAINER, f"https://{ORIGIN_DOMAIN}/{web_base_path}/")
    if "3X-UI" not in panel_html and "login" not in panel_html.lower() and "html" not in panel_html.lower():
        log("Origin panel is not serving valid HTML!", "error")
        return False
    log("Origin panel is up and healthy!", "success")

    # -------------------------------------------------------------------------
    # Step 2: Create remote backup and download locally
    # -------------------------------------------------------------------------
    log("=== STEP 2: Running backup mode on vps-maint-panel ===", "info")
    backup_config = {
        "deploy_mode": "backup",
        "vps_host": "127.0.0.1",
        "vps_port": ORIGIN_PORT,
        "vps_user": "root",
        "vps_password": "root",
        "vps_auth_type": "password",
        "backup_vps_host": "127.0.0.1",
        "backup_vps_port": ORIGIN_PORT,
        "backup_vps_user": "root",
        "backup_vps_password": "root",
    }

    ok_bk, res_bk = await run_deployment(backup_config, log)
    if not ok_bk:
        log("Backup creation failed!", "error")
        return False

    backup_name = res_bk.get("backup_name")
    if not backup_name:
        log("Backup result missing 'backup_name'!", "error")
        return False

    local_backup_path = os.path.join(REPO_ROOT, "backups_panel", backup_name)
    if not os.path.isfile(local_backup_path) or os.path.getsize(local_backup_path) == 0:
        log(f"Backup archive not found or empty: {local_backup_path}", "error")
        return False

    log(f"Local backup archive created: {local_backup_path} ({os.path.getsize(local_backup_path)} bytes)", "success")

    # Verify archive contents
    with tarfile.open(local_backup_path, "r:*") as tar:
        names = tar.getnames()
        has_db = any("3x-ui/db/x-ui.db" in n for n in names)
        has_caddy = any("caddy/Caddyfile" in n for n in names)
        has_compose = any("docker-compose.yml" in n for n in names)

    if not (has_db and has_caddy and has_compose):
        log(f"Archive missing critical files! (db={has_db}, caddy={has_caddy}, compose={has_compose})", "error")
        return False
    log("Backup archive structure verified: contains database, Caddyfile and compose file.", "success")

    # -------------------------------------------------------------------------
    # Step 3: Run recovery mode onto target container with domain rewrite
    # -------------------------------------------------------------------------
    log("=== STEP 3: Running recovery mode onto vps-maint-recovery ===", "info")
    recovery_config = {
        "deploy_mode": "recovery",
        "vps_host": "127.0.0.1",
        "vps_port": TARGET_PORT,
        "vps_user": "root",
        "vps_password": "root",
        "vps_auth_type": "password",
        "recovery_vps_host": "127.0.0.1",
        "recovery_vps_port": TARGET_PORT,
        "recovery_vps_user": "root",
        "recovery_vps_password": "root",
        "recovery_domain": TARGET_DOMAIN,
        "recovery_backup_file": backup_name,
        "recovery_xui_username": ADMIN_USER,
        "recovery_xui_password": ADMIN_PASS,
        "bundle_source_dir": prepare_test_repo("panel"),
    }

    try:
        ok_rec, res_rec = await run_deployment(recovery_config, log)
        if not ok_rec:
            log("Panel recovery failed!", "error")
            return False

        if not check_inner_containers_running(TARGET_CONTAINER, ["3xui", "caddy", "nginx-decoy"]):
            return False

        # Verify panel is accessible under new domain
        rec_panel_html = fetch_panel_html(TARGET_CONTAINER, f"https://{TARGET_DOMAIN}/{web_base_path}/")
        if "3X-UI" not in rec_panel_html and "login" not in rec_panel_html.lower() and "html" not in rec_panel_html.lower():
            log("Restored panel is not serving valid HTML!", "error")
            return False
        log("Restored panel is accessible under target domain!", "success")

        log("==================================================", "success")
        log("🎉 TEST PANEL BACKUP & RECOVERY PASSED! 🎉", "success")
        log("==================================================", "success")
        return True

    finally:
        # Cleanup test backup file from disk
        if os.path.exists(local_backup_path):
            try:
                os.remove(local_backup_path)
                log(f"Cleaned up test backup file {local_backup_path}", "info")
            except OSError:
                pass


def main():
    ok = asyncio.run(test_panel_backup_and_recovery())
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()

