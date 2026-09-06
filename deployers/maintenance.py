"""Maintenance deployment operations (Phase C1 of REFACTORING.md).

Behavioral slice extracted from ssh_deployer.py::run_deployment:

- backup                  (remote panel backup + SCP download)
- recovery                (restore from backup archive, domain rewrite)
- update / update_3xui    (3X-UI panel version update)
- restart_panel / restart_server
- restart_sub / update_sub / backup_sub / rollback_sub (subscription server)

run_deployment keeps its public signature and delegates to this module.
No behavior changes: bodies moved verbatim.
"""

import os
import re
import shlex
import tarfile
from typing import Callable, Dict, Any, Optional, Tuple

from ssh_deployer import (
    PANEL_DOMAIN_REWRITE_SCRIPT,
    REPO_ROOT,
    SSHDeployer,
    LEGACY_COMPOSE_REWRITE_CMD,
    LEGACY_TEMPLATES_SYMLINK_CMD,
    _change_remote_ssh_port,
    _deploy_sub_server,
    _perform_remote_backup,
    _sub_server_sync_cmd,
    get_bundle_bytes,
)


# ---------------------------------------------------------------------------
# Panel: backup / recovery / update / restart
# ---------------------------------------------------------------------------

async def deploy_backup(
    config: Dict[str, Any],
    log: Callable[[str, str], None],
    cancel_check: Optional[Callable[[], bool]] = None,
) -> Tuple[bool, Dict[str, Any]]:
    host = (config.get("backup_vps_host") or config.get("vps_host") or "").strip()
    port = int(config.get("backup_vps_port") or config.get("vps_port") or 22)
    user = (config.get("backup_vps_user") or config.get("vps_user") or "root").strip()
    password = config.get("backup_vps_password") if config.get("backup_vps_password") is not None else config.get("vps_password", "")
    key_data = config.get("backup_vps_key") if config.get("backup_vps_key") is not None else config.get("vps_key", "")

    if not host:
        log("[ERROR] Remote domain host is required for backup mode.", "error")
        return False, {}

    raw_backup_name = config.get("backup_name", "").strip()
    if not raw_backup_name:
        import datetime
        now_str = datetime.datetime.now().strftime("%Y-%m-%d_%H%M%S")
        raw_backup_name = f"{host}_{now_str}.tar.gz" if host else f"backup_{now_str}.tar.gz"
    elif not any(raw_backup_name.endswith(ext) for ext in [".tar.gz", ".tgz", ".zip", ".tar"]):
        raw_backup_name = f"{raw_backup_name}.tar.gz"

    backup_name = os.path.basename(raw_backup_name)

    log(f"Starting remote backup process for server {host}:{port}...", "info")
    async with SSHDeployer(host, port, user, password, key_data, cancel_check=cancel_check) as deployer:
        log(f"Connecting to {host}:{port}...", "info")
        ok, msg = await deployer.test_connection()
        if not ok:
            log(f"[ERROR] SSH connection failed: {msg}", "error")
            return False, {}

        bk_ok, bk_local_path, file_size_mb = await _perform_remote_backup(deployer, backup_name, log)
        if not bk_ok:
            return False, {}

        log("=========================================", "success")
        log("🎉 BACKUP CREATED AND DOWNLOADED SUCCESSFULLY!", "success")
        log(f"Local backup location: ./backups_panel/{backup_name} ({file_size_mb} MB)", "success")
        log("=========================================", "success")

        return True, {
            "deploy_mode": "backup",
            "backup_host": host,
            "backup_name": backup_name,
            "backup_path": f"./backups_panel/{backup_name}",
            "file_size": f"{file_size_mb} MB"
        }


async def deploy_recovery(
    config: Dict[str, Any],
    log: Callable[[str, str], None],
    cancel_check: Optional[Callable[[], bool]] = None,
) -> Tuple[bool, Dict[str, Any]]:
    host = (config.get("recovery_vps_host") or config.get("vps_host") or "").strip()
    port = int(config.get("recovery_vps_port") or config.get("vps_port") or 22)
    user = (config.get("recovery_vps_user") or config.get("vps_user") or "root").strip()
    password = config.get("recovery_vps_password") if config.get("recovery_vps_password") is not None else config.get("vps_password", "")
    key_data = config.get("recovery_vps_key") if config.get("recovery_vps_key") is not None else config.get("vps_key", "")
    backup_filename = config.get("recovery_backup_file", "").strip()
    recovery_panel_user = config.get("recovery_xui_username", "").strip() or "admin"
    recovery_panel_pass = config.get("recovery_xui_password", "").strip() or "admin"
    recovery_creds_provided = bool(config.get("recovery_xui_username") or config.get("recovery_xui_password"))

    if not host:
        log("[ERROR] Target domain host is required for recovery mode.", "error")
        return False, {}

    if not backup_filename:
        log("[ERROR] Backup file must be selected for recovery mode.", "error")
        return False, {}

    repo_root = REPO_ROOT
    local_backup_path = os.path.join(repo_root, "backups_panel", os.path.basename(backup_filename))

    if not os.path.isfile(local_backup_path):
        log(f"[ERROR] Selected backup archive '{backup_filename}' not found in ./backups_panel/", "error")
        return False, {}

    # Inspect the backup archive locally: old domain + hidden web base path
    old_domain = ""
    web_base_path = ""
    try:
        with tarfile.open(local_backup_path, "r:*") as tar:
            for member in tar.getmembers():
                if member.name.endswith("Caddyfile"):
                    ef = tar.extractfile(member)
                    if ef:
                        caddy_text = ef.read().decode("utf-8", errors="replace")
                        m_dom = re.search(r'email 3xui@([A-Za-z0-9.-]+)', caddy_text)
                        if not m_dom:
                            m_dom = re.search(r'^([A-Za-z0-9.-]+):[0-9]+', caddy_text, re.MULTILINE)
                        if m_dom:
                            old_domain = m_dom.group(1).strip()
                        m_path = re.search(r'@web_base_path\s+path\s+/([A-Za-z0-9_-]+)', caddy_text)
                        if m_path:
                            web_base_path = m_path.group(1)
                    break
    except Exception:
        pass

    domain_changed = bool(old_domain) and old_domain.lower() != host.lower()
    if domain_changed and not recovery_creds_provided:
        log(f"[ERROR] Domain change detected in the backup (old: '{old_domain}' -> new: '{host}'). "
            f"Rewriting the domain inside the 3x-UI panel is done via its HTTP API and requires the "
            f"panel admin credentials. Fill in the 3X-UI login/password fields in the recovery form "
            f"(default for a fresh deployment is admin/admin).", "error")
        return False, {}

    with open(local_backup_path, "rb") as f:
        backup_bytes = f.read()

    remote_dir = "/opt/3x-ui-bootstRUp"

    log(f"Starting Recovery process for server {host}:{port} using '{backup_filename}'...", "info")
    async with SSHDeployer(host, port, user, password, key_data, cancel_check=cancel_check) as deployer:
        log(f"Connecting to {host}:{port}...", "info")
        ok, msg = await deployer.test_connection()
        if not ok:
            log(f"[ERROR] SSH connection failed: {msg}", "error")
            return False, {}

        log(f"Syncing local tool files to {host}...", "info")
        bundle_bytes = get_bundle_bytes()
        sync_cmd = f"mkdir -p {remote_dir} && tar -xzf - -C {remote_dir}"
        rc, sync_out = await deployer.exec_command(sync_cmd, lambda m: log(m, "info"), stdin_data=bundle_bytes)
        if rc != 0:
            log(f"[ERROR] Failed to transfer tool files to {host}: {sync_out}", "error")
            return False, {}

        log(f"Uploading backup archive ({len(backup_bytes)} bytes) to {host}...", "info")
        upload_cmd = "cat > /tmp/recovery_backup.tar.gz"
        rc, up_out = await deployer.exec_command(upload_cmd, lambda m: log(m, "info"), stdin_data=backup_bytes)
        if rc != 0:
            log(f"[ERROR] Failed to upload backup archive to {host}: {up_out}", "error")
            return False, {}

        log("Extracting backup and launching Docker Compose...", "info")

        new_domain_str = shlex.quote(host)
        remote_script = (
            "set -e\n"
            "cd /opt/3x-ui-bootstRUp\n"
            "COMPOSE_FILE=\"working/docker-compose/docker-compose.yml\"\n"
            "if [ -f \"$COMPOSE_FILE\" ]; then\n"
            "  docker compose -f \"$COMPOSE_FILE\" --project-directory . down --remove-orphans 2>/dev/null || true\n"
            "fi\n"
            "docker stop 3xui caddy nginx-decoy 2>/dev/null || true\n"
            "docker rm 3xui caddy nginx-decoy 2>/dev/null || true\n"
            "rm -rf ./working && mkdir -p ./working\n"
            "tar -xzf /tmp/recovery_backup.tar.gz -C ./working\n"
            "rm -f /tmp/recovery_backup.tar.gz\n"
            "\n"
            "# Domain replacement if domain changed\n"
            "CADDY_FILE=\"working/caddy/Caddyfile\"\n"
            "NEW_DOM=" + new_domain_str + "\n"
            "if [ -f \"$CADDY_FILE\" ]; then\n"
            "  OLD_DOMAIN=$(grep -oE 'email 3xui@[A-Za-z0-9.-]+' \"$CADDY_FILE\" | head -n 1 | cut -d'@' -f2 || true)\n"
            "  if [ -z \"$OLD_DOMAIN\" ]; then\n"
            "    OLD_DOMAIN=$(grep -oE '^[A-Za-z0-9.-]+:[0-9]+' \"$CADDY_FILE\" | head -n 1 | cut -d':' -f1 || true)\n"
            "  fi\n"
            "  if [ -n \"$OLD_DOMAIN\" ] && [ \"$OLD_DOMAIN\" != \"$NEW_DOM\" ]; then\n"
            "    echo \"[INFO] Domain change detected from '$OLD_DOMAIN' to '$NEW_DOM'. Updating Caddyfile & configs...\"\n"
            "    ESC_OLD=$(printf '%s\\n' \"$OLD_DOMAIN\" | sed -e 's/[\\/&]/\\\\&/g')\n"
            "    ESC_NEW=$(printf '%s\\n' \"$NEW_DOM\" | sed -e 's/[\\/&]/\\\\&/g')\n"
            "    sed -i \"s/$ESC_OLD/$ESC_NEW/g\" \"$CADDY_FILE\"\n"
            "    [ -f \"working/nginx-decoy/default.conf\" ] && sed -i \"s/$ESC_OLD/$ESC_NEW/g\" \"working/nginx-decoy/default.conf\" || true\n"
            "    rm -rf working/.caddy_data 2>/dev/null || true\n"
            "    docker volume rm caddy_data 2>/dev/null || true\n"
            "  fi\n"
            "  WEB_PATH=$(grep -oE '@web_base_path path /[^ /]+' \"$CADDY_FILE\" | head -n 1 | awk '{print $3}' | tr -d '/' || true)\n"
            "  if [ -n \"$WEB_PATH\" ]; then\n"
            "    echo \"RECOVERY_WEB_PATH=$WEB_PATH\"\n"
            "  fi\n"
            "fi\n"
            "\n"
            + LEGACY_COMPOSE_REWRITE_CMD +
            "\n"
            "if [ -f \"$COMPOSE_FILE\" ]; then\n"
            "  docker compose -f \"$COMPOSE_FILE\" --project-directory . up -d\n"
            "else\n"
            "  echo \"[ERROR] docker-compose.yml not found in backup!\"\n"
            "  exit 1\n"
            "fi\n"
        )

        rc, out = await deployer.exec_command(f"bash -c {shlex.quote(remote_script)}", lambda m: log(m, "info"))
        if rc != 0:
            log(f"[ERROR] Recovery extraction or container startup failed: {out}", "error")
            return False, {}

        m_path_out = re.search(r'RECOVERY_WEB_PATH=([A-Za-z0-9_-]+)', out)
        if m_path_out:
            web_base_path = m_path_out.group(1)

        if not web_base_path:
            try:
                with tarfile.open(local_backup_path, "r:*") as tar:
                    for member in tar.getmembers():
                        if member.name.endswith("Caddyfile"):
                            ef = tar.extractfile(member)
                            if ef:
                                caddy_text = ef.read().decode("utf-8", errors="replace")
                                m_path = re.search(r'@web_base_path\s+path\s+/([A-Za-z0-9_-]+)', caddy_text)
                                if m_path:
                                    web_base_path = m_path.group(1)
                                    break
            except Exception:
                pass

        # Rewrite the domain inside the running 3x-UI panel via its HTTP API
        # (serverName / client `add` / externalProxy dest / subURI), so the
        # regenerated subscriptions point to the new host. No SQLite access.
        if domain_changed:
            log(f"Rewriting panel domain '{old_domain}' -> '{host}' via the 3x-UI HTTP API...", "info")
            rc_scr, scr_out = await deployer.exec_command(
                "cat > /tmp/panel_domain_rewrite.sh",
                lambda m: log(m, "info"),
                stdin_data=PANEL_DOMAIN_REWRITE_SCRIPT.encode("utf-8"),
            )
            if rc_scr != 0:
                log(f"[ERROR] Failed to upload the domain-rewrite script: {scr_out}", "error")
                return False, {}
            rewrite_env = (
                f"RECOVERY_OLD_DOMAIN={shlex.quote(old_domain)} "
                f"RECOVERY_NEW_DOM={shlex.quote(host)} "
                f"RECOVERY_PANEL_USER={shlex.quote(recovery_panel_user)} "
                f"RECOVERY_PANEL_PASS={shlex.quote(recovery_panel_pass)}"
            )
            rc_rewrite, out_rewrite = await deployer.exec_command(
                f"{rewrite_env} bash /tmp/panel_domain_rewrite.sh",
                lambda m: log(m, "info"),
            )
            if rc_rewrite != 0:
                log(f"[ERROR] Panel domain rewrite failed: {out_rewrite}", "error")
                return False, {}
            log("✅ Panel domain rewritten (serverName / client add / subURI).", "success")

        xui_url = f"https://{host}/{web_base_path}/" if web_base_path else f"https://{host}/"

        log("=========================================", "success")
        log("🎉 RECOVERY COMPLETED SUCCESSFULLY!", "success")
        log(f"Server {host} restored from backup '{backup_filename}'", "success")
        log(f"Panel URL: {xui_url}", "success")
        log("=========================================", "success")

        return True, {
            "deploy_mode": "recovery",
            "recovery_host": host,
            "backup_file": backup_filename,
            "xui_url": xui_url
        }


async def deploy_update(
    config: Dict[str, Any],
    log: Callable[[str, str], None],
    cancel_check: Optional[Callable[[], bool]] = None,
    change_ssh_port: bool = False,
    new_ssh_port: Optional[int] = None,
    updated_ssh_ports: Optional[Dict[str, int]] = None,
    prepare_decoy_files: Optional[Callable[..., Optional[Dict[str, bytes]]]] = None,
) -> Tuple[bool, Dict[str, Any]]:
    host = (config.get("update_vps_host") or config.get("vps_host") or "").strip()
    port = int(config.get("update_vps_port") or config.get("vps_port") or 22)
    user = (config.get("update_vps_user") or config.get("vps_user") or "root").strip()
    password = config.get("update_vps_password") if config.get("update_vps_password") is not None else config.get("vps_password", "")
    key_data = config.get("update_vps_key") if config.get("update_vps_key") is not None else config.get("vps_key", "")
    target_version = (config.get("update_xui_version") or config.get("xui_version")).strip()

    if not host:
        log("[ERROR] Remote host is required for update mode.", "error")
        return False, {}

    update_decoy_tpl = (config.get("update_decoy_template") or "").strip()
    update_decoy_files = None
    if update_decoy_tpl:
        update_decoy_files = prepare_decoy_files(update_decoy_tpl, "Update Decoy")

    remote_dir = "/opt/3x-ui-bootstRUp"

    log(f"Starting 3X-UI update process for server {host}:{port} to version '{target_version}'...", "info")
    async with SSHDeployer(host, port, user, password, key_data, cancel_check=cancel_check) as deployer:
        log(f"Connecting to {host}:{port}...", "info")
        ok, msg = await deployer.test_connection()
        if not ok:
            log(f"[ERROR] SSH connection failed: {msg}", "error")
            return False, {}

        log(f"Syncing local tool scripts to {host}:{remote_dir}...", "info")
        bundle_bytes = get_bundle_bytes(decoy_files=update_decoy_files)
        sync_cmd = f"mkdir -p {remote_dir} && tar -xzf - -C {remote_dir}"
        rc, sync_out = await deployer.exec_command(sync_cmd, lambda m: log(m, "info"), stdin_data=bundle_bytes)
        if rc != 0:
            log(f"[ERROR] Failed to transfer scripts to {host}: {sync_out}", "error")
            return False, {}

        # --- Pre-update backup: create on server and download locally ---
        log("📦 Creating pre-update backup before version change...", "info")
        import datetime as _dt
        now_str = _dt.datetime.now().strftime("%Y-%m-%d_%H%M%S")
        backup_name = f"{host}_pre-update_{now_str}.tar.gz"

        bk_ok, bk_local_path, file_size_mb = await _perform_remote_backup(deployer, backup_name, log)
        if not bk_ok:
            return False, {}

        log(f"✅ Pre-update backup saved: ./backups_panel/{backup_name} ({file_size_mb} MB)", "success")
        # --- End of pre-update backup ---

        log(f"Executing remote panel_update.sh {target_version}...", "info")
        version_str = shlex.quote(target_version)
        remote_script = (
            "set -e\n"
            "WORK_DIR=\"/opt/3x-ui-bootstRUp\"\n"
            "if [ ! -d \"$WORK_DIR\" ]; then\n"
            "  if [ -d \"./working\" ]; then WORK_DIR=\".\"; else WORK_DIR=\"$(pwd)\"; fi\n"
            "fi\n"
            "cd \"$WORK_DIR\"\n"
            "chmod +x panel_update.sh panel_backup.sh 2>/dev/null || true\n"
            "bash panel_update.sh " + version_str + "\n"
        )

        rc, out = await deployer.exec_command(f"bash -c {shlex.quote(remote_script)}", lambda m: log(m, "info"))
        if rc != 0:
            log(f"[ERROR] Remote 3X-UI update failed: {out}", "error")
            return False, {}

        decoy_updated = False
        if update_decoy_files:
            log("🎨 Updating decoy site on remote server...", "info")
            decoy_script = (
                "set -e\n"
                "WORK_DIR=\"/opt/3x-ui-bootstRUp\"\n"
                "if [ ! -d \"$WORK_DIR\" ]; then WORK_DIR=\".\"; fi\n"
                "cd \"$WORK_DIR\"\n"
                "rm -rf working/nginx-decoy/html\n"
                "cp -r common/templates/nginx-decoy/html working/nginx-decoy/html\n"
                "COMPOSE_FILE=\"working/docker-compose/docker-compose.yml\"\n"
                "if [ -f \"$COMPOSE_FILE\" ]; then\n"
                "  docker compose -f \"$COMPOSE_FILE\" --project-directory . restart nginx-decoy 2>/dev/null || true\n"
                "else\n"
                "  docker restart nginx-decoy 2>/dev/null || true\n"
                "fi\n"
            )
            rc_decoy, _ = await deployer.exec_command(f"bash -c {shlex.quote(decoy_script)}", lambda m: log(m, "info"))
            if rc_decoy == 0:
                log("✅ Decoy site updated and nginx-decoy restarted.", "success")
                decoy_updated = True
            else:
                log("[WARN] Failed to update decoy site. Panel update itself succeeded.", "warn")

        web_base_path = ""
        target_domain = ""
        caddy_cmd = "cat /opt/3x-ui-bootstRUp/working/caddy/Caddyfile 2>/dev/null || cat working/caddy/Caddyfile 2>/dev/null || true"
        rc_cad, cad_out = await deployer.exec_command(caddy_cmd)
        if rc_cad == 0 and cad_out:
            m_path = re.search(r'@web_base_path\s+path\s+/([A-Za-z0-9_-]+)', cad_out)
            if m_path:
                web_base_path = m_path.group(1)
            m_dom = re.search(r'email\s+[a-zA-Z0-9._%+-]+@([a-zA-Z0-9.-]+)', cad_out)
            if m_dom:
                target_domain = m_dom.group(1).strip()

        xui_url = f"https://{host}/{web_base_path}/" if web_base_path else f"https://{host}/"

        log("=========================================", "success")
        log("🎉 3X-UI PANEL UPDATED SUCCESSFULLY!", "success")
        log(f"Server: {host}:{port}", "success")
        log(f"New 3x-ui version: {target_version}", "success")
        if decoy_updated:
            log(f"Decoy site: updated to '{update_decoy_tpl}'", "success")
        log(f"Panel URL: {xui_url}", "success")
        log(f"Pre-update backup: ./backups_panel/{backup_name} ({file_size_mb} MB)", "success")
        log("=========================================", "success")

        if change_ssh_port and new_ssh_port:
            if await _change_remote_ssh_port(host, port, new_ssh_port, user, password, key_data, log, cancel_check):
                updated_ssh_ports[host] = new_ssh_port
                if target_domain and target_domain != host:
                    updated_ssh_ports[target_domain] = new_ssh_port

        res_data = {
            "deploy_mode": "update_3xui",
            "update_host": host,
            "target_domain": target_domain,
            "xui_version": target_version,
            "xui_url": xui_url,
            "backup_name": backup_name,
            "backup_path": f"./backups_panel/{backup_name}",
            "backup_size": f"{file_size_mb} MB",
            "decoy_updated": decoy_updated,
        }
        if updated_ssh_ports:
            res_data["new_ssh_port"] = new_ssh_port
            res_data["updated_ssh_ports"] = updated_ssh_ports

        return True, res_data


async def deploy_restart(
    config: Dict[str, Any],
    log: Callable[[str, str], None],
    cancel_check: Optional[Callable[[], bool]] = None,
) -> Tuple[bool, Dict[str, Any]]:
    deploy_mode = config.get("deploy_mode", "").strip()
    host = (config.get("update_vps_host") or config.get("vps_host") or "").strip()
    port = int(config.get("update_vps_port") or config.get("vps_port") or 22)
    user = (config.get("update_vps_user") or config.get("vps_user") or "root").strip()
    password = config.get("update_vps_password") if config.get("update_vps_password") is not None else config.get("vps_password", "")
    key_data = config.get("update_vps_key") if config.get("update_vps_key") is not None else config.get("vps_key", "")

    if not host:
        log(f"[ERROR] Remote host is required for {deploy_mode}.", "error")
        return False, {}

    log(f"Starting {deploy_mode} process for server {host}:{port}...", "info")
    async with SSHDeployer(host, port, user, password, key_data, cancel_check=cancel_check) as deployer:
        log(f"Connecting to {host}:{port}...", "info")
        ok, msg = await deployer.test_connection()
        if not ok:
            log(f"[ERROR] SSH connection failed: {msg}", "error")
            return False, {}

        if deploy_mode == "restart_panel":
            log("Restarting 3x-ui panel via docker compose...", "info")
            remote_script = (
                "set -e\n"
                "WORK_DIR=\"/opt/3x-ui-bootstRUp\"\n"
                "if [ ! -d \"$WORK_DIR\" ]; then\n"
                "  if [ -d \"./working\" ]; then WORK_DIR=\".\"; else WORK_DIR=\"$(pwd)\"; fi\n"
                "fi\n"
                "cd \"$WORK_DIR\"\n"
                "COMPOSE_FILE=\"working/docker-compose/docker-compose.yml\"\n"
                "if [ -f \"$COMPOSE_FILE\" ]; then\n"
                "  docker compose -f \"$COMPOSE_FILE\" --project-directory . down --remove-orphans 2>/dev/null || true\n"
                "fi\n"
                "docker stop 3xui caddy nginx-decoy 2>/dev/null || true\n"
                "docker rm 3xui caddy nginx-decoy 2>/dev/null || true\n"
                + LEGACY_TEMPLATES_SYMLINK_CMD +
                "docker compose -f \"$COMPOSE_FILE\" --project-directory . up -d\n"
            )
            rc, out = await deployer.exec_command(f"bash -c {shlex.quote(remote_script)}", lambda m: log(m, "info"))
            if rc != 0:
                log(f"[ERROR] Panel restart failed: {out}", "error")
                return False, {}

            log("✅ Panel restarted successfully!", "success")
            return True, {"deploy_mode": deploy_mode, "host": host}

        elif deploy_mode == "restart_server":
            log("Restarting server...", "info")
            rc, out = await deployer.exec_command("sudo reboot || reboot")
            log("✅ Reboot command sent!", "success")
            return True, {"deploy_mode": deploy_mode, "host": host}


# ---------------------------------------------------------------------------
# Subscription server: restart / update / backup / rollback
# ---------------------------------------------------------------------------

async def deploy_sub_ops(
    config: Dict[str, Any],
    log: Callable[[str, str], None],
    cancel_check: Optional[Callable[[], bool]] = None,
    change_ssh_port: bool = False,
    new_ssh_port: Optional[int] = None,
    updated_ssh_ports: Optional[Dict[str, int]] = None,
    prepare_decoy_files: Optional[Callable[..., Optional[Dict[str, bytes]]]] = None,
) -> Tuple[bool, Dict[str, Any]]:
    deploy_mode = config.get("deploy_mode", "").strip()
    sub_host = (config.get("sub_vps_host") or config.get("vps_host") or "").strip()
    sub_port = int(config.get("sub_vps_port") or config.get("vps_port") or 22)
    sub_user = (config.get("sub_vps_user") or config.get("vps_user") or "root").strip()
    sub_password = config.get("sub_vps_password") if config.get("sub_vps_password") is not None else config.get("vps_password", "")
    sub_key = config.get("sub_vps_key") if config.get("sub_vps_key") is not None else config.get("vps_key", "")

    if not sub_host:
        log(f"[ERROR] Subscription Server host is required for {deploy_mode}.", "error")
        return False, {}

    log(f"Starting {deploy_mode} process for Subscription Server {sub_host}:{sub_port}...", "info")
    async with SSHDeployer(sub_host, sub_port, sub_user, sub_password, sub_key, cancel_check=cancel_check) as deployer:
        log(f"Connecting to {sub_host}:{sub_port}...", "info")
        ok, msg = await deployer.test_connection()
        if not ok:
            log(f"[ERROR] SSH connection failed: {msg}", "error")
            return False, {}

        if deploy_mode == "restart_sub":
            log(f"Syncing local tool files to Subscription Server {sub_host}...", "info")
            bundle_bytes = get_bundle_bytes(source_dir=config.get("bundle_source_dir"))
            sync_cmd = _sub_server_sync_cmd("/opt/3x-ui-bootstRUp", preserve=True)
            rc, sync_out = await deployer.exec_command(sync_cmd, lambda m: log(m, "info"), stdin_data=bundle_bytes)
            if rc != 0:
                log(f"[ERROR] Failed to transfer tool files to {sub_host}: {sync_out}", "error")
                return False, {}

            log("Restarting sub-server containers via sub-server/restart.sh...", "info")
            remote_script = (
                "set -e\n"
                "WORK_DIR=\"/opt/3x-ui-bootstRUp\"\n"
                "if [ ! -d \"$WORK_DIR\" ]; then\n"
                "  if [ -d \"./working\" ]; then WORK_DIR=\".\"; else WORK_DIR=\"$(pwd)\"; fi\n"
                "fi\n"
                "cd \"$WORK_DIR\"\n"
                "bash sub-server/restart.sh\n"
            )
            rc, out = await deployer.exec_command(f"bash -c {shlex.quote(remote_script)}", lambda m: log(m, "info"))
            if rc != 0:
                log(f"[ERROR] Sub-server restart failed: {out}", "error")
                return False, {}

            log("✅ Subscription Server restarted successfully!", "success")
            return True, {"deploy_mode": deploy_mode, "sub_host": sub_host}

        if deploy_mode == "update_sub":
            import datetime
            now_str = datetime.datetime.now().strftime("%Y-%m-%d_%H%M%S")
            pre_backup_name = f"{sub_host}_pre-update_{now_str}.tar.gz"
            log("📦 Creating full pre-update backup before changing Subscription Server files...", "info")
            bk_ok, bk_local_path, file_size_mb = await _perform_remote_backup(
                deployer, pre_backup_name, log, target="sub_server"
            )
            if not bk_ok:
                log("[ERROR] Update aborted because the pre-update backup could not be created.", "error")
                return False, {}
            log(
                f"✅ Pre-update backup saved: ./backups_sub_server/{pre_backup_name} ({file_size_mb} MB)",
                "success",
            )

            sub_env = {
                "UPDATE_SUB_SERVER": "1",
                # setup.sh reads DOMAIN/path/URLs/admin credentials from the
                # existing generated compose/Caddy config in update mode.
            }
            update_sub_decoy_tpl = (config.get("update_sub_decoy_template") or "").strip()
            update_sub_decoy_files = (
                prepare_decoy_files(update_sub_decoy_tpl, "Subscription Server Update")
                if update_sub_decoy_tpl else None
            )
            if update_sub_decoy_files is not None:
                # Explicitly selected a decoy template: setup.sh must apply it
                # (otherwise it preserves the currently deployed decoy site).
                sub_env["UPDATE_SUB_DECOY"] = "1"
            log("Updating Subscription Server files and containers; client data will be preserved...", "info")
            ok_sub, out_sub = await _deploy_sub_server(
                sub_host, sub_port, sub_user, sub_password, sub_key, sub_env, log,
                cancel_check=cancel_check,
                bundle_source_dir=config.get("bundle_source_dir"),
                decoy_files=update_sub_decoy_files,
            )
            if not ok_sub:
                log(f"[ERROR] Subscription Server update failed: {out_sub}", "error")
                return False, {}
            log("✅ Subscription Server updated successfully; clients and nodes preserved!", "success")
            sub_domain = (config.get("sub_domain") or "").strip()
            caddy_cmd = "cat /opt/3x-ui-bootstRUp/working/caddy/Caddyfile 2>/dev/null || cat working/caddy/Caddyfile 2>/dev/null || true"
            rc_cad, cad_out = await deployer.exec_command(caddy_cmd)
            if rc_cad == 0 and cad_out:
                m_dom = re.search(r'email\s+[a-zA-Z0-9._%+-]+@([a-zA-Z0-9.-]+)', cad_out)
                if m_dom:
                    sub_domain = m_dom.group(1).strip()

            if change_ssh_port and new_ssh_port:
                if await _change_remote_ssh_port(sub_host, sub_port, new_ssh_port, sub_user, sub_password, sub_key, log, cancel_check):
                    updated_ssh_ports[sub_host] = new_ssh_port
                    if sub_domain and sub_domain != sub_host:
                        updated_ssh_ports[sub_domain] = new_ssh_port

            res_data = {
                "deploy_mode": deploy_mode,
                "sub_host": sub_host,
                "sub_domain": sub_domain,
                "pre_update_backup": f"./backups_sub_server/{pre_backup_name}",
            }
            if updated_ssh_ports:
                res_data["new_ssh_port"] = new_ssh_port
                res_data["updated_ssh_ports"] = updated_ssh_ports

            return True, res_data

        if deploy_mode == "backup_sub":
            raw_backup_name = config.get("backup_name", "").strip()
            if not raw_backup_name:
                import datetime
                now_str = datetime.datetime.now().strftime("%Y-%m-%d_%H%M%S")
                raw_backup_name = f"{sub_host}_sub_{now_str}.tar.gz"
            elif not any(raw_backup_name.endswith(ext) for ext in [".tar.gz", ".tgz", ".zip", ".tar"]):
                raw_backup_name = f"{raw_backup_name}.tar.gz"
            backup_name = os.path.basename(raw_backup_name)

            bk_ok, bk_local_path, file_size_mb = await _perform_remote_backup(deployer, backup_name, log, target="sub_server")
            if not bk_ok:
                return False, {}

            log("=========================================", "success")
            log("🎉 SUB-SERVER BACKUP CREATED AND DOWNLOADED SUCCESSFULLY!", "success")
            log(f"Local backup location: ./backups_sub_server/{backup_name} ({file_size_mb} MB)", "success")
            log("=========================================", "success")

            return True, {
                "deploy_mode": "backup_sub",
                "sub_host": sub_host,
                "backup_name": backup_name,
                "backup_path": f"./backups_sub_server/{backup_name}",
                "file_size": f"{file_size_mb} MB"
            }

        if deploy_mode == "rollback_sub":
            backup_filename = config.get("rollback_sub_backup_file", "").strip()
            if not backup_filename:
                log("[ERROR] Backup file must be selected for rollback_sub mode.", "error")
                return False, {}

            repo_root = REPO_ROOT
            local_backup_path = os.path.join(repo_root, "backups_sub_server", os.path.basename(backup_filename))

            if not os.path.isfile(local_backup_path):
                log(f"[ERROR] Selected backup archive '{backup_filename}' not found in ./backups_sub_server/", "error")
                return False, {}

            with open(local_backup_path, "rb") as f:
                backup_bytes = f.read()

            log(f"Uploading sub-server backup archive ({len(backup_bytes)} bytes) to {sub_host}...", "info")
            upload_cmd = "cat > /tmp/sub_rollback_backup.tar.gz"
            rc, up_out = await deployer.exec_command(upload_cmd, lambda m: log(m, "info"), stdin_data=backup_bytes)
            if rc != 0:
                log(f"[ERROR] Failed to upload backup archive to {sub_host}: {up_out}", "error")
                return False, {}

            log("Restoring configs and restarting Subscription Server containers...", "info")
            remote_script = (
                "set -e\n"
                "WORK_DIR=\"/opt/3x-ui-bootstRUp\"\n"
                "if [ ! -d \"$WORK_DIR\" ]; then\n"
                "  if [ -d \"./working\" ]; then WORK_DIR=\".\"; else WORK_DIR=\"$(pwd)\"; fi\n"
                "fi\n"
                "cd \"$WORK_DIR\"\n"
                "COMPOSE_FILE=\"working/docker-compose/docker-compose.yml\"\n"
                "if [ -f \"$COMPOSE_FILE\" ]; then\n"
                "  docker compose -f \"$COMPOSE_FILE\" --project-directory . down --remove-orphans 2>/dev/null || true\n"
                "fi\n"
                "docker stop subs-server sub-caddy sub-nginx-decoy 2>/dev/null || true\n"
                "docker rm subs-server sub-caddy sub-nginx-decoy 2>/dev/null || true\n"
                "rm -rf /tmp/sub_restore && mkdir -p /tmp/sub_restore\n"
                "tar -xzf /tmp/sub_rollback_backup.tar.gz -C /tmp/sub_restore\n"
                "rm -f /tmp/sub_rollback_backup.tar.gz\n"
                "mkdir -p sub-server working/caddy working/docker-compose\n"
                "[ -f /tmp/sub_restore/subs.yml ] && cp /tmp/sub_restore/subs.yml sub-server/subs.yml || true\n"
                "[ -f /tmp/sub_restore/force-subs.yml ] && cp /tmp/sub_restore/force-subs.yml sub-server/force-subs.yml || true\n"
                "[ -f /tmp/sub_restore/nodes.json ] && cp /tmp/sub_restore/nodes.json sub-server/nodes.json || true\n"
                "[ -f /tmp/sub_restore/working/Caddyfile ] && cp /tmp/sub_restore/working/Caddyfile working/caddy/Caddyfile || true\n"
                "[ -f /tmp/sub_restore/working/docker-compose.yml ] && cp /tmp/sub_restore/working/docker-compose.yml working/docker-compose/docker-compose.yml || true\n"
                "if [ -d /tmp/sub_restore/.caddy_data ]; then\n"
                "  rm -rf .caddy_data && cp -r /tmp/sub_restore/.caddy_data .caddy_data\n"
                "fi\n"
                "rm -rf /tmp/sub_restore\n"
                "if [ -f \"$COMPOSE_FILE\" ]; then\n"
                "  docker compose -f \"$COMPOSE_FILE\" --project-directory . up -d\n"
                "else\n"
                "  echo \"[ERROR] docker-compose.yml not found after restore!\"\n"
                "  exit 1\n"
                "fi\n"
                "SECRET_SUB_PATH=$(grep -oE 'handle /[A-Za-z0-9_-]+' working/caddy/Caddyfile 2>/dev/null | head -n 1 | sed 's|handle /||' || true)\n"
                "if [ -n \"$SECRET_SUB_PATH\" ]; then\n"
                "  echo \"SUB_SECRET_PATH=$SECRET_SUB_PATH\"\n"
                "fi\n"
            )
            rc, out = await deployer.exec_command(f"bash -c {shlex.quote(remote_script)}", lambda m: log(m, "info"))
            if rc != 0:
                log(f"[ERROR] Sub-server rollback failed: {out}", "error")
                return False, {}

            sub_secret_path = ""
            m_sub_out = re.search(r'SUB_SECRET_PATH=([A-Za-z0-9_-]+)', out)
            if m_sub_out:
                sub_secret_path = m_sub_out.group(1)

            log("=========================================", "success")
            log("🎉 SUB-SERVER ROLLBACK COMPLETED SUCCESSFULLY!", "success")
            log(f"Subscription Server {sub_host} restored from '{backup_filename}'", "success")
            if sub_secret_path:
                log(f"Subscriptions base URL: https://{sub_host}/{sub_secret_path}", "success")
            log("=========================================", "success")

            result = {
                "deploy_mode": "rollback_sub",
                "sub_host": sub_host,
                "backup_file": backup_filename
            }
            if sub_secret_path:
                result["sub_base_url"] = f"https://{sub_host}/{sub_secret_path}"
            return True, result