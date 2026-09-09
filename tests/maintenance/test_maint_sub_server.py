#!/usr/bin/env python3
"""
Test: Maintenance - Sub-Server Lifecycle (backup_sub, restart_sub, update_sub, rollback_sub)
1. Deploys Sub-Server on vps-maint-sub (maint-sub.test)
2. Executes backup_sub mode -> verifies local archive in ./backups_sub_server/
3. Executes restart_sub mode -> verifies containers restart cleanly
4. Executes update_sub mode -> verifies pre-update backup and update success
5. Modifies nodes.json and executes rollback_sub mode -> verifies original state restored
6. Cleans up downloaded backup archives
"""

import asyncio
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
    log,
)

CONTAINER = "vps-maint-sub"
PORT = 2263
DOMAIN = "maint-sub.test"
SECRET_SUB_PATH = "maint-subs"
ADMIN_USER = "subadmin"
ADMIN_PASS = "SubAdminPassword123!"


def get_container_start_time(c_name: str) -> str:
    res = subprocess.run(
        ["docker", "exec", CONTAINER, "docker", "inspect", c_name, "--format", "{{.State.StartedAt}}"],
        capture_output=True, text=True
    )
    return res.stdout.strip()


async def test_sub_server_maintenance() -> bool:
    ensure_test_containers_running(CONTAINER)

    created_backups = []

    try:
        # ---------------------------------------------------------------------
        # Step 1: Initial deployment of Sub-Server
        # ---------------------------------------------------------------------
        log("=== STEP 1: Deploying Sub-Server on vps-maint-sub ===", "info")
        init_config = {
            "deploy_mode": "sub_only",
            "vps_host": "127.0.0.1",
            "vps_port": PORT,
            "vps_user": "root",
            "vps_password": "root",
            "vps_auth_type": "password",
            "sub_vps_host": "127.0.0.1",
            "sub_vps_port": PORT,
            "sub_vps_user": "root",
            "sub_vps_password": "root",
            "sub_domain": DOMAIN,
            "sub_secret_path": SECRET_SUB_PATH,
            "sub_russian_url": "https://ru-node.test/sub",
            "sub_foreign_url": "https://foreign-node.test/sub",
            "sub_proxy_clients": "user1-maint",
            "sub_freedom_clients": "user2-maint",
            "sub_admin_user": ADMIN_USER,
            "sub_admin_password": ADMIN_PASS,
            "bundle_source_dir": prepare_test_repo("panel", "sub-server"),
        }

        ok, res = await run_deployment(init_config, log)
        if not ok:
            log("Initial Sub-Server deployment failed!", "error")
            return False

        if not check_inner_containers_running(CONTAINER, ["subs-server", "sub-caddy", "sub-nginx-decoy"]):
            return False
        log("Initial Sub-Server deployment succeeded!", "success")

        # ---------------------------------------------------------------------
        # Step 2: backup_sub
        # ---------------------------------------------------------------------
        log("=== STEP 2: Creating sub-server backup (backup_sub) ===", "info")
        backup_config = {
            "deploy_mode": "backup_sub",
            "vps_host": "127.0.0.1",
            "vps_port": PORT,
            "vps_user": "root",
            "vps_password": "root",
            "vps_auth_type": "password",
            "sub_vps_host": "127.0.0.1",
            "sub_vps_port": PORT,
            "sub_vps_user": "root",
            "sub_vps_password": "root",
        }

        ok_bk, res_bk = await run_deployment(backup_config, log)
        if not ok_bk:
            log("backup_sub mode failed!", "error")
            return False

        backup_name = res_bk.get("backup_name")
        if not backup_name:
            log("Result missing 'backup_name'!", "error")
            return False

        local_bk_path = os.path.join(REPO_ROOT, "backups_sub_server", backup_name)
        if not os.path.isfile(local_bk_path) or os.path.getsize(local_bk_path) == 0:
            log(f"Sub-server backup file not found or empty: {local_bk_path}", "error")
            return False
        created_backups.append(local_bk_path)
        log(f"Sub-server backup created: {local_bk_path}", "success")

        # ---------------------------------------------------------------------
        # Step 3: restart_sub
        # ---------------------------------------------------------------------
        log("=== STEP 3: Restarting sub-server (restart_sub) ===", "info")
        before_starts = {
            c: get_container_start_time(c)
            for c in ["subs-server", "sub-caddy", "sub-nginx-decoy"]
        }
        time.sleep(1.5)

        restart_config = {
            "deploy_mode": "restart_sub",
            "vps_host": "127.0.0.1",
            "vps_port": PORT,
            "vps_user": "root",
            "vps_password": "root",
            "vps_auth_type": "password",
            "sub_vps_host": "127.0.0.1",
            "sub_vps_port": PORT,
            "sub_vps_user": "root",
            "sub_vps_password": "root",
            "bundle_source_dir": prepare_test_repo("panel", "sub-server"),
        }

        ok_rst, res_rst = await run_deployment(restart_config, log)
        if not ok_rst:
            log("restart_sub mode failed!", "error")
            return False

        after_starts = {
            c: get_container_start_time(c)
            for c in ["subs-server", "sub-caddy", "sub-nginx-decoy"]
        }
        for c in ["subs-server", "sub-caddy", "sub-nginx-decoy"]:
            if before_starts[c] == after_starts[c]:
                log(f"Container {c} did not change start time after restart_sub!", "error")
                return False
            log(f"Container {c} restarted successfully.", "success")

        # ---------------------------------------------------------------------
        # Step 4: update_sub
        # ---------------------------------------------------------------------
        log("=== STEP 4: Updating sub-server (update_sub) ===", "info")
        update_config = {
            "deploy_mode": "update_sub",
            "vps_host": "127.0.0.1",
            "vps_port": PORT,
            "vps_user": "root",
            "vps_password": "root",
            "vps_auth_type": "password",
            "sub_vps_host": "127.0.0.1",
            "sub_vps_port": PORT,
            "sub_vps_user": "root",
            "sub_vps_password": "root",
            "sub_domain": DOMAIN,
            "bundle_source_dir": prepare_test_repo("panel", "sub-server"),
        }

        ok_up, res_up = await run_deployment(update_config, log)
        if not ok_up:
            log("update_sub mode failed!", "error")
            return False

        pre_bk = res_up.get("pre_update_backup")
        if pre_bk:
            created_backups.append(os.path.join(REPO_ROOT, pre_bk.lstrip("./")))
        log("update_sub completed successfully!", "success")

        # ---------------------------------------------------------------------
        # Step 5: Corrupt nodes.json and execute rollback_sub
        # ---------------------------------------------------------------------
        log("=== STEP 5: Testing rollback_sub ===", "info")
        # Read original nodes.json content
        orig_nodes = subprocess.run(
            ["docker", "exec", CONTAINER, "cat", "/opt/3x-ui-bootstRUp/sub-server/nodes.json"],
            capture_output=True, text=True, check=True
        ).stdout.strip()
        log(f"Original nodes.json length: {len(orig_nodes)} chars", "info")

        # Overwrite nodes.json with empty list
        subprocess.run(
            ["docker", "exec", CONTAINER, "bash", "-c", "echo '[]' > /opt/3x-ui-bootstRUp/sub-server/nodes.json"],
            check=True
        )

        rollback_config = {
            "deploy_mode": "rollback_sub",
            "vps_host": "127.0.0.1",
            "vps_port": PORT,
            "vps_user": "root",
            "vps_password": "root",
            "vps_auth_type": "password",
            "sub_vps_host": "127.0.0.1",
            "sub_vps_port": PORT,
            "sub_vps_user": "root",
            "sub_vps_password": "root",
            "rollback_sub_backup_file": backup_name,
        }

        ok_rb, res_rb = await run_deployment(rollback_config, log)
        if not ok_rb:
            log("rollback_sub mode failed!", "error")
            return False

        # Verify nodes.json restored
        restored_nodes = subprocess.run(
            ["docker", "exec", CONTAINER, "cat", "/opt/3x-ui-bootstRUp/sub-server/nodes.json"],
            capture_output=True, text=True, check=True
        ).stdout.strip()

        if "user1-maint" not in restored_nodes:
            log(f"nodes.json was not restored to original! Content: {restored_nodes}", "error")
            return False
        log("nodes.json was successfully restored to pre-corruption state!", "success")

        log("==================================================", "success")
        log("🎉 TEST SUB-SERVER MAINTENANCE PASSED! 🎉", "success")
        log("==================================================", "success")
        return True

    finally:
        for p in created_backups:
            if os.path.exists(p):
                try:
                    os.remove(p)
                    log(f"Cleaned up backup file {p}", "info")
                except OSError:
                    pass


def main():
    ok = asyncio.run(test_sub_server_maintenance())
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()

