"""Standalone subscription server deployment (Phase C3 of REFACTORING.md).

Extracted from ssh_deployer.py::run_deployment ``sub_only`` branch.
Transport helpers (_deploy_sub_server, _sub_server_sync_cmd) remain
in ssh_deployer.py to avoid circular imports; they will move to
core/ssh_client.py in C5.
"""

import os
import re
from typing import Callable, Dict, Any, Optional, Tuple

from ssh_deployer import (
    NodeConfig,
    REPO_ROOT,
    _change_remote_ssh_port,
    _deploy_sub_server,
    derive_sub_server_path,
    extract_domain_from_url,
    resolve_sub_server_urls,
)


async def deploy_sub_only(
    config: Dict[str, Any],
    log: Callable[[str, str], None],
    cancel_check: Optional[Callable[[], bool]] = None,
    bundle_dir: Optional[str] = None,
    change_ssh_port: bool = False,
    new_ssh_port: Optional[int] = None,
    updated_ssh_ports: Optional[Dict[str, int]] = None,
    prepare_decoy_files: Optional[Callable[..., Optional[Dict[str, bytes]]]] = None,
) -> Tuple[bool, Dict[str, Any]]:
    sub_host = config.get("sub_vps_host", "").strip() or config.get("vps_host", "").strip()
    sub_port = int(config.get("sub_vps_port") or config.get("vps_port") or 22)
    sub_user = config.get("sub_vps_user", "").strip() or config.get("vps_user", "root").strip()
    sub_password = config.get("sub_vps_password", config.get("vps_password", ""))
    sub_key = config.get("sub_vps_key", config.get("vps_key", ""))
    sub_domain = config.get("sub_domain", "").strip() or sub_host
    sub_secret_raw = (config.get("sub_secret_path", "") or config.get("sub_secret", "") or "").strip()
    sub_secret_path = derive_sub_server_path(sub_secret_raw) if sub_secret_raw else ""

    sub_russian_url = config.get("sub_russian_url", "").strip()
    sub_foreign_url = config.get("sub_foreign_url", "").strip()

    proxy_raw = config.get("sub_proxy_clients", "").strip()
    freedom_raw = config.get("sub_freedom_clients", "").strip()
    proxy_clients = [n.strip() for n in re.split(r'[\s,]+', proxy_raw) if n.strip()]
    freedom_clients = [n.strip() for n in re.split(r'[\s,]+', freedom_raw) if n.strip()]

    log(f"Starting deployment of Subscription Server on {sub_host}...", "info")
    sub_admin_user = config.get("sub_admin_user", "").strip()
    sub_admin_password = config.get("sub_admin_password", "").strip()
    sub_proxy_url, sub_foreign_url, _ = resolve_sub_server_urls(sub_russian_url, sub_foreign_url)
    ru_domain = config.get("proxy_domain") or config.get("proxy_host") or extract_domain_from_url(sub_proxy_url)
    fr_domain = config.get("freedom_domain") or config.get("freedom_host") or extract_domain_from_url(sub_foreign_url)
    sub_env = {
        "DOMAIN": sub_domain,
        "SECRET_SUB_PATH": sub_secret_path,
        "RUSSIAN_SUB_URL": sub_proxy_url,
        "FOREIGN_SUB_URL": sub_foreign_url,
        "PROXY_DOMAIN": ru_domain,
        "FREEDOM_DOMAIN": fr_domain,
        "PROXY_CLIENTS": " ".join(proxy_clients),
        "FREEDOM_CLIENTS": " ".join(freedom_clients),
        "ADMIN_USER": sub_admin_user,
        "ADMIN_PASSWORD": sub_admin_password
    }

    sub_decoy_files = prepare_decoy_files(config.get("sub_decoy_template") or config.get("decoy_template"), "Subscription Server")
    ok_sub, out_sub = await _deploy_sub_server(NodeConfig(sub_host, sub_port, sub_user, sub_password, sub_key, sub_env, cancel_check=cancel_check, bundle_source_dir=bundle_dir, decoy_files=sub_decoy_files), log)
    if not ok_sub:
        log("[ERROR] Failed to deploy Subscription Server.", "error")
        return False, {}

    if change_ssh_port and new_ssh_port:
        if await _change_remote_ssh_port(sub_host, sub_port, new_ssh_port, sub_user, sub_password, sub_key, log, cancel_check):
            updated_ssh_ports[sub_host] = new_ssh_port
            if sub_domain and sub_domain != sub_host:
                updated_ssh_ports[sub_domain] = new_ssh_port

    base_sub_url = f"https://{sub_domain}/{sub_secret_path}"
    sub_clients = []
    for c in proxy_clients:
        sub_clients.append({
            "name": c,
            "sub_url": f"{base_sub_url}/{c}",
            "group": f"Proxy ({ru_domain})" if ru_domain else "Proxy"
        })
    for c in freedom_clients:
        sub_clients.append({
            "name": c,
            "sub_url": f"{base_sub_url}/{c}",
            "group": f"Freedom ({fr_domain})" if fr_domain else "Freedom"
        })

    log("=========================================", "success")
    log("🎉 SUBSCRIPTION SERVER DEPLOYED SUCCESSFULLY!", "success")
    log(f"Subscription URL Base: {base_sub_url}/<username>", "success")
    log(f"Panel: {base_sub_url}  (admin: {sub_admin_user} / password: ••••••••)", "success")
    log("=========================================", "success")

    result_data = {
        "deploy_mode": "sub_only",
        "sub_domain": sub_domain,
        "sub_secret_path": sub_secret_path,
        "sub_base_url": base_sub_url,
        "sub_admin_user": sub_admin_user,
        "sub_admin_password": sub_admin_password,
        "clients": sub_clients
    }
    if updated_ssh_ports:
        result_data["new_ssh_port"] = new_ssh_port
        result_data["updated_ssh_ports"] = updated_ssh_ports
    return True, result_data
