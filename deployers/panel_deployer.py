"""Panel node deployment orchestration (Phase C3 of REFACTORING.md).

Extracted from ssh_deployer.py::run_deployment:

- deploy_single      — single / proxy_only / freedom_only / freedom_component
- deploy_freedom_sub — freedom_sub (freedom node + subscription server, 2 stages)
- deploy_cascade     — cascade / cascade_sub (freedom + proxy [+ sub-server])

Transport helpers (_deploy_node, _deploy_sub_server) remain in ssh_deployer.py
to avoid circular imports; they move to core/ssh_client.py in C5.
"""

import hashlib
import re
from typing import Callable, Dict, Any, Optional, Tuple

from ssh_deployer import (
    _change_remote_ssh_port,
    _deploy_node,
    _deploy_sub_server,
    derive_sub_path,
    derive_sub_server_path,
    extract_domain_from_url,
    parse_deployment_results,
    resolve_sub_server_urls,
)


async def deploy_single(
    config: Dict[str, Any],
    log: Callable[[str, str], None],
    cancel_check: Optional[Callable[[], bool]] = None,
    bundle_dir: Optional[str] = None,
    change_ssh_port: bool = False,
    new_ssh_port: Optional[int] = None,
    updated_ssh_ports: Optional[Dict[str, int]] = None,
    prepare_decoy_files: Optional[Callable[..., Optional[Dict[str, bytes]]]] = None,
) -> Tuple[bool, Dict[str, Any]]:
    deploy_mode = config.get("deploy_mode", "").strip()

    tcp_raw = config.get("client_tcp_list", "").strip()
    xhttp_raw = config.get("client_xhttp_list", "").strip()
    clients_tcp_str = " ".join([name.strip() for name in re.split(r'[\s,]+', tcp_raw) if name.strip()])
    clients_xhttp_str = " ".join([name.strip() for name in re.split(r'[\s,]+', xhttp_raw) if name.strip()])

    sub_secret = config.get("sub_secret", "").strip()
    web_base_path = hashlib.md5(f"{sub_secret}-panel".encode('utf-8')).hexdigest()[:16]
    log("Generated secure deployment configuration.", "info")

    host = config.get("vps_host", "").strip()
    port = int(config.get("vps_port") or 22)
    user = config.get("vps_user", "root").strip()
    password = config.get("vps_password", "")
    key_data = config.get("vps_key", "")
    log(f"Starting deployment process on single server {host}...", "info")
    cascade_choice = "n"
    node_type_choice = "1"
    if deploy_mode in ["freedom_only", "freedom_component"]:
        cascade_choice = "y"
        node_type_choice = "1"
        default_freedom_client = config.get("freedom_client_name", "").strip() or "local-proxy-node-client"
        xhttp_names = [n.strip() for n in re.split(r'[\s,]+', clients_xhttp_str) if n.strip()]
        if default_freedom_client not in xhttp_names:
            xhttp_names.append(default_freedom_client)
        clients_xhttp_str = " ".join(xhttp_names)
        single_decoy_tpl = config.get("decoy_template") or config.get("freedom_decoy_template")
        single_label = "Freedom Node"
    elif deploy_mode == "proxy_only":
        cascade_choice = "y"
        node_type_choice = "2"
        single_decoy_tpl = config.get("decoy_template") or config.get("proxy_decoy_template")
        single_label = "Proxy Node"
    else:
        single_decoy_tpl = config.get("decoy_template")
        single_label = "Single Node"

    foreign_sub_url = config.get("foreign_sub_url", "").strip() if deploy_mode == "proxy_only" else ""
    target_domain = config.get("domain", "").strip() or host

    xui_username = config.get("xui_username", "").strip()
    xui_password = config.get("xui_password", "").strip()
    xui_version = config.get("xui_version", "").strip()

    env_vars = {
        "DOMAIN": target_domain,
        "USERNAME": xui_username,
        "USER_PASSWORD": xui_password,
        "XUI_VERSION": xui_version,
        "SECRET_PHRASE": sub_secret,
        "CLIENTS_TCP_LIST": clients_tcp_str,
        "CLIENTS_XHTTP_LIST": clients_xhttp_str,
        "CASCADE_CHOICE": cascade_choice,
        "NODE_TYPE_CHOICE": node_type_choice,
        "FOREIGN_SUB_URL": foreign_sub_url
    }

    single_decoy_files = prepare_decoy_files(single_decoy_tpl, single_label)
    ok, out = await _deploy_node(host, port, user, password, key_data, env_vars, log, cancel_check=cancel_check, bundle_source_dir=bundle_dir, decoy_files=single_decoy_files)
    parsed_xui_url, parsed_clients = parse_deployment_results(out) if ok else ("", [])
    
    if ok and change_ssh_port and new_ssh_port:
        if await _change_remote_ssh_port(host, port, new_ssh_port, user, password, key_data, log, cancel_check):
            updated_ssh_ports[host] = new_ssh_port
            if target_domain and target_domain != host:
                updated_ssh_ports[target_domain] = new_ssh_port

    final_xui_url = parsed_xui_url or f"https://{target_domain}/{web_base_path}/"
    result_data = {
        "deploy_mode": deploy_mode,
        "xui_url": final_xui_url,
        "xui_username": xui_username,
        "xui_password": xui_password,
        "sub_secret": sub_secret,
        "domain": target_domain,
        "clients": parsed_clients
    }
    if updated_ssh_ports:
        result_data["new_ssh_port"] = new_ssh_port
        result_data["updated_ssh_ports"] = updated_ssh_ports
    return ok, result_data


async def deploy_freedom_sub(
    config: Dict[str, Any],
    log: Callable[[str, str], None],
    cancel_check: Optional[Callable[[], bool]] = None,
    bundle_dir: Optional[str] = None,
    change_ssh_port: bool = False,
    new_ssh_port: Optional[int] = None,
    updated_ssh_ports: Optional[Dict[str, int]] = None,
    prepare_decoy_files: Optional[Callable[..., Optional[Dict[str, bytes]]]] = None,
) -> Tuple[bool, Dict[str, Any]]:
    deploy_mode = config.get("deploy_mode", "").strip()

    tcp_raw = config.get("client_tcp_list", "").strip()
    xhttp_raw = config.get("client_xhttp_list", "").strip()
    clients_tcp_str = " ".join([name.strip() for name in re.split(r'[\s,]+', tcp_raw) if name.strip()])
    clients_xhttp_str = " ".join([name.strip() for name in re.split(r'[\s,]+', xhttp_raw) if name.strip()])

    sub_secret = config.get("sub_secret", "").strip()
    web_base_path = hashlib.md5(f"{sub_secret}-panel".encode('utf-8')).hexdigest()[:16]

    xui_username = config.get("xui_username", "").strip()
    xui_password = config.get("xui_password", "").strip()
    xui_version = config.get("xui_version", "").strip()

    host = (config.get("vps_host_for_ssh") or config.get("vps_host") or "").strip()
    port = int(config.get("vps_port") or 22)
    user = config.get("vps_user", "root").strip()
    password = config.get("vps_password", "")
    key_data = config.get("vps_key", "")
    target_domain = config.get("domain", "").strip() or host

    log("╔════════════════════════════════════════════╗", "info")
    log("║ [STAGE 1/2] FREEDOM NODE (Foreign Server)    ║", "info")
    log("╠════════════════════════════════════════════╣", "info")
    log(f"║ CURRENTLY DEPLOYING: {host:35} ║", "info")
    log("╚════════════════════════════════════════════╝", "info")

    env_vars = {
        "DOMAIN": target_domain,
        "USERNAME": xui_username,
        "USER_PASSWORD": xui_password,
        "XUI_VERSION": xui_version,
        "SECRET_PHRASE": sub_secret,
        "CLIENTS_TCP_LIST": clients_tcp_str,
        "CLIENTS_XHTTP_LIST": clients_xhttp_str,
        "CASCADE_CHOICE": "y",
        "NODE_TYPE_CHOICE": "1",
        "FOREIGN_SUB_URL": ""
    }

    freedom_decoy_files = prepare_decoy_files(config.get("decoy_template") or config.get("freedom_decoy_template"), "Freedom Node")
    ok1, out1 = await _deploy_node(host, port, user, password, key_data, env_vars, log, cancel_check=cancel_check, bundle_source_dir=bundle_dir, decoy_files=freedom_decoy_files)
    if not ok1:
        log("[ERROR] Stage 1 failed: Could not deploy Freedom Node.", "error")
        return False, {}
    log("", "success")
    log("✅ [STAGE 1 COMPLETE] Freedom Node deployed successfully!", "success")
    log("", "success")

    if change_ssh_port and new_ssh_port:
        if await _change_remote_ssh_port(host, port, new_ssh_port, user, password, key_data, log, cancel_check):
            updated_ssh_ports[host] = new_ssh_port
            if target_domain and target_domain != host:
                updated_ssh_ports[target_domain] = new_ssh_port

    parsed_xui_url, parsed_clients = parse_deployment_results(out1) if ok1 else ("", [])
    final_xui_url = parsed_xui_url or f"https://{target_domain}/{web_base_path}/"

    freedom_sub_base = ""
    if parsed_clients and parsed_clients[0].get("sub_url"):
        freedom_sub_base = parsed_clients[0]["sub_url"].rsplit("/", 1)[0]
    if not freedom_sub_base:
        freedom_sub_base = f"https://{target_domain}/{derive_sub_path(sub_secret)}"

    log("╔════════════════════════════════════════════╗", "info")
    log("║ [STAGE 2/2] SUBSCRIPTION SERVER (Relay)   ║", "info")
    log("╠════════════════════════════════════════════╣", "info")
    log(f"║ CURRENTLY DEPLOYING: {config.get('sub_vps_host', '').strip():35} ║", "info")
    log("╚════════════════════════════════════════════╝", "info")

    sub_host = config.get("sub_vps_host", "").strip()
    sub_port = int(config.get("sub_vps_port") or 22)
    sub_user = config.get("sub_vps_user", "root").strip() or "root"
    sub_password = config.get("sub_vps_password", "")
    sub_key = config.get("sub_vps_key", "")
    sub_domain = config.get("sub_domain", "").strip() or sub_host
    sub_secret_raw = (config.get("sub_secret_path", "") or "subs").strip()
    sub_secret_path = derive_sub_server_path(sub_secret_raw)

    if not sub_host:
        log("[ERROR] Stage 2 failed: Subscription Server host address is required.", "error")
        return False, {}

    freedom_client_names = [n.strip() for n in re.split(r'[\s,]+', f"{clients_tcp_str} {clients_xhttp_str}") if n.strip()]

    sub_admin_user = config.get("sub_admin_user", "").strip()
    sub_admin_password = config.get("sub_admin_password", "").strip()

    resolved_proxy, resolved_freedom, extra_sub_env = resolve_sub_server_urls(
        "", freedom_sub_base,
    )
    fr_domain = target_domain or freedom_host or extract_domain_from_url(resolved_freedom)

    sub_env = {
        "DOMAIN": sub_domain,
        "SECRET_SUB_PATH": sub_secret_path,
        "RUSSIAN_SUB_URL": resolved_proxy,
        "FOREIGN_SUB_URL": resolved_freedom,
        "PROXY_DOMAIN": "",
        "FREEDOM_DOMAIN": fr_domain,
        "PROXY_CLIENTS": "",
        "FREEDOM_CLIENTS": " ".join(freedom_client_names),
        "ADMIN_USER": sub_admin_user,
        "ADMIN_PASSWORD": sub_admin_password,
        **extra_sub_env,
    }

    sub_decoy_files = prepare_decoy_files(config.get("sub_decoy_template") or config.get("decoy_template"), "Subscription Server")
    sub_target = sub_host
    effective_sub_port = updated_ssh_ports.get(sub_target, sub_port)
    ok2, out2 = await _deploy_sub_server(sub_target, effective_sub_port, sub_user, sub_password, sub_key, sub_env, log, cancel_check=cancel_check, bundle_source_dir=bundle_dir, decoy_files=sub_decoy_files)
    if not ok2:
        log("[ERROR] Stage 2 failed: Subscription Server deployment failed.", "error")
        return False, {}

    if change_ssh_port and new_ssh_port:
        if await _change_remote_ssh_port(sub_target, effective_sub_port, new_ssh_port, sub_user, sub_password, sub_key, log, cancel_check):
            updated_ssh_ports[sub_host] = new_ssh_port
            if sub_domain and sub_domain != sub_host:
                updated_ssh_ports[sub_domain] = new_ssh_port

    log("", "success")
    log("✅ [STAGE 2 COMPLETE] Subscription Server deployed successfully!", "success")
    log("", "success")

    base_sub_url = f"https://{sub_domain}/{sub_secret_path}"
    result_data = {
        "deploy_mode": deploy_mode,
        "xui_url": final_xui_url,
        "xui_username": xui_username,
        "xui_password": xui_password,
        "sub_secret": sub_secret,
        "domain": target_domain,
        "freedom_xui_url": final_xui_url,
        "freedom_username": xui_username,
        "freedom_password": xui_password,
        "freedom_sub_secret": sub_secret,
        "freedom_domain": target_domain,
        "sub_domain": sub_domain,
        "sub_secret_path": sub_secret_path,
        "sub_base_url": base_sub_url,
        "sub_admin_user": sub_admin_user,
        "sub_admin_password": sub_admin_password,
        "clients": parsed_clients
    }

    for cl in parsed_clients:
        cl["sub_server_url"] = f"{base_sub_url}/{cl['name']}"

    if updated_ssh_ports:
        result_data["new_ssh_port"] = new_ssh_port
        result_data["updated_ssh_ports"] = updated_ssh_ports

    log("╔════════════════════════════════════════════╗", "success")
    log("║         🎉 ALL STAGES COMPLETED! 🎉         ║", "success")
    log("╚════════════════════════════════════════════╝", "success")
    log("", "success")
    log(f"Panel (Freedom Node): {final_xui_url}", "success")
    log(f"  - Admin User: {xui_username}", "success")
    log(f"  - Admin Password: ••••••••", "success")
    log(f"Subscription Server: https://{sub_domain}/{sub_secret_path}/<username>", "success")
    log(f"  - Admin: {sub_admin_user or 'admin'} / password: ••••••••", "success")
    log("=========================================", "success")
    return True, result_data


async def deploy_cascade(
    config: Dict[str, Any],
    log: Callable[[str, str], None],
    cancel_check: Optional[Callable[[], bool]] = None,
    bundle_dir: Optional[str] = None,
    change_ssh_port: bool = False,
    new_ssh_port: Optional[int] = None,
    updated_ssh_ports: Optional[Dict[str, int]] = None,
    prepare_decoy_files: Optional[Callable[..., Optional[Dict[str, bytes]]]] = None,
) -> Tuple[bool, Dict[str, Any]]:
    deploy_mode = config.get("deploy_mode", "").strip()

    tcp_raw = config.get("client_tcp_list", "").strip()
    xhttp_raw = config.get("client_xhttp_list", "").strip()
    clients_tcp_str = " ".join([name.strip() for name in re.split(r'[\s,]+', tcp_raw) if name.strip()])
    clients_xhttp_str = " ".join([name.strip() for name in re.split(r'[\s,]+', xhttp_raw) if name.strip()])

    xui_version = config.get("xui_version", "").strip()

    # Cascade modes: "cascade" or "cascade_sub"
    freedom_host = config.get("freedom_host", "").strip()
    freedom_port = int(config.get("freedom_port") or 22)
    freedom_user = config.get("freedom_user", "root").strip()
    freedom_password = config.get("freedom_password", "")
    freedom_key = config.get("freedom_key", "")
    freedom_xui_user = config.get("freedom_xui_username", "").strip()
    freedom_xui_pass = config.get("freedom_xui_password", "").strip()
    freedom_secret = config.get("freedom_sub_secret", "").strip()
    freedom_client = config.get("freedom_client_name", "").strip() or "local-proxy-node-client"
    freedom_xui_version = config.get("freedom_xui_version", "").strip() or xui_version

    proxy_host = config.get("proxy_host", "").strip()
    proxy_port = int(config.get("proxy_port") or 22)
    proxy_user = config.get("proxy_user", "root").strip()
    proxy_password = config.get("proxy_password", "")
    proxy_key = config.get("proxy_key", "")
    proxy_xui_user = config.get("proxy_xui_username", "").strip()
    proxy_xui_pass = config.get("proxy_xui_password", "").strip()
    proxy_secret = config.get("proxy_sub_secret", "").strip()
    proxy_xui_version = config.get("proxy_xui_version", "").strip() or xui_version

    proxy_tcp_raw = config.get("proxy_client_tcp_list", "").strip() or tcp_raw
    proxy_xhttp_raw = config.get("proxy_client_xhttp_list", "").strip() or xhttp_raw
    proxy_clients_tcp_str = " ".join([name.strip() for name in re.split(r'[\s,]+', proxy_tcp_raw) if name.strip()])
    proxy_clients_xhttp_str = " ".join([name.strip() for name in re.split(r'[\s,]+', proxy_xhttp_raw) if name.strip()])

    freedom_host_for_ssh = config.get("freedom_host_for_ssh", "").strip()
    proxy_host_for_ssh = config.get("proxy_host_for_ssh", "").strip()

    total_stages = "3" if deploy_mode == "cascade_sub" else "2"

    log("╔════════════════════════════════════════════╗", "info")
    log(f"║ [STAGE 1/{total_stages}] FREEDOM NODE (Foreign Server)    ║", "info")
    log("╠════════════════════════════════════════════╣", "info")
    log(f"║ CURRENTLY DEPLOYING: {freedom_host:35} ║", "info")
    log("╚════════════════════════════════════════════╝", "info")
    freedom_env = {
        "DOMAIN": freedom_host,
        "USERNAME": freedom_xui_user,
        "USER_PASSWORD": freedom_xui_pass,
        "XUI_VERSION": freedom_xui_version,
        "SECRET_PHRASE": freedom_secret,
        "CLIENTS_TCP_LIST": "",
        "CLIENTS_XHTTP_LIST": freedom_client,
        "CASCADE_CHOICE": "y",
        "NODE_TYPE_CHOICE": "1"
    }

    freedom_decoy_files = prepare_decoy_files(config.get("freedom_decoy_template") or config.get("decoy_template"), "Freedom Node")
    fr_target = freedom_host_for_ssh or freedom_host
    ok1, out1 = await _deploy_node(fr_target, freedom_port, freedom_user, freedom_password, freedom_key, freedom_env, log, cancel_check=cancel_check, bundle_source_dir=bundle_dir, decoy_files=freedom_decoy_files)
    if not ok1:
        log("[ERROR] Stage 1 failed: Could not deploy foreign server.", "error")
        return False, {}
    log("", "success")
    log("✅ [STAGE 1 COMPLETE] Freedom Node deployed successfully!", "success")
    log("", "success")

    if change_ssh_port and new_ssh_port:
        if await _change_remote_ssh_port(fr_target, freedom_port, new_ssh_port, freedom_user, freedom_password, freedom_key, log, cancel_check):
            updated_ssh_ports[freedom_host] = new_ssh_port
            if freedom_host_for_ssh:
                updated_ssh_ports[freedom_host_for_ssh] = new_ssh_port

    freedom_xui_url, freedom_clients = parse_deployment_results(out1)

    freedom_sub_url = ""
    if freedom_clients and len(freedom_clients) > 0:
        freedom_sub_url = freedom_clients[0].get("sub_url", "")
    if not freedom_sub_url:
        freedom_sub_url = f"https://{freedom_host}/{derive_sub_path(freedom_secret)}/{freedom_client}"
    log(f"Cascade subscription URL generated for client '{freedom_client}'.", "info")

    log("╔════════════════════════════════════════════╗", "info")
    log(f"║ [STAGE 2/{total_stages}] PROXY NODE (Local Server)       ║", "info")
    log("╠════════════════════════════════════════════╣", "info")
    log(f"║ CURRENTLY DEPLOYING: {proxy_host:35} ║", "info")
    log("╚════════════════════════════════════════════╝", "info")
    proxy_env = {
        "DOMAIN": proxy_host,
        "USERNAME": proxy_xui_user,
        "USER_PASSWORD": proxy_xui_pass,
        "XUI_VERSION": proxy_xui_version,
        "SECRET_PHRASE": proxy_secret,
        "CLIENTS_TCP_LIST": proxy_clients_tcp_str,
        "CLIENTS_XHTTP_LIST": proxy_clients_xhttp_str,
        "CASCADE_CHOICE": "y",
        "NODE_TYPE_CHOICE": "2",
        "FOREIGN_SUB_URL": freedom_sub_url
    }

    proxy_decoy_files = prepare_decoy_files(config.get("proxy_decoy_template") or config.get("decoy_template"), "Proxy Node")
    px_target = proxy_host_for_ssh or proxy_host
    effective_proxy_port = updated_ssh_ports.get(px_target, proxy_port)
    ok2, out2 = await _deploy_node(px_target, effective_proxy_port, proxy_user, proxy_password, proxy_key, proxy_env, log, cancel_check=cancel_check, bundle_source_dir=bundle_dir, decoy_files=proxy_decoy_files)
    if not ok2:
        log("[ERROR] Stage 2 failed: Could not deploy local server.", "error")
        return False, {}
    log("", "success")
    log("✅ [STAGE 2 COMPLETE] Proxy Node deployed successfully!", "success")
    log("", "success")

    if change_ssh_port and new_ssh_port:
        if await _change_remote_ssh_port(px_target, effective_proxy_port, new_ssh_port, proxy_user, proxy_password, proxy_key, log, cancel_check):
            updated_ssh_ports[proxy_host] = new_ssh_port
            if proxy_host_for_ssh:
                updated_ssh_ports[proxy_host_for_ssh] = new_ssh_port
    parsed_xui_url, parsed_clients = parse_deployment_results(out2) if ok2 else ("", [])
    proxy_web_path = hashlib.md5(f"{proxy_secret}-panel".encode('utf-8')).hexdigest()[:16]
    final_xui_url = parsed_xui_url or f"https://{proxy_host}/{proxy_web_path}/"
    freedom_web_path = hashlib.md5(f"{freedom_secret}-panel".encode('utf-8')).hexdigest()[:16]
    freedom_final_xui_url = freedom_xui_url or f"https://{freedom_host}/{freedom_web_path}/"

    result_data = {
        "deploy_mode": deploy_mode,
        "is_cascade": True,
        "xui_url": final_xui_url,
        "xui_username": proxy_xui_user,
        "xui_password": proxy_xui_pass,
        "sub_secret": proxy_secret,
        "domain": proxy_host,
        "freedom_xui_url": freedom_final_xui_url,
        "freedom_username": freedom_xui_user,
        "freedom_password": freedom_xui_pass,
        "freedom_sub_secret": freedom_secret,
        "freedom_domain": freedom_host,
        "clients": parsed_clients
    }

    if deploy_mode == "cascade_sub":
        log("╔════════════════════════════════════════════╗", "info")
        log("║ [STAGE 3/3] SUBSCRIPTION SERVER (Relay)   ║", "info")
        log("╠════════════════════════════════════════════╣", "info")
        log(f"║ CURRENTLY DEPLOYING: {config.get('sub_vps_host', '').strip():35} ║", "info")
        log("╚════════════════════════════════════════════╝", "info")

        sub_host = config.get("sub_vps_host", "").strip()
        sub_port = int(config.get("sub_vps_port") or 22)
        sub_user = config.get("sub_vps_user", "root").strip() or "root"
        sub_password = config.get("sub_vps_password", "")
        sub_key = config.get("sub_vps_key", "")
        sub_domain = config.get("sub_domain", "").strip() or sub_host
        sub_secret_raw = (config.get("sub_secret_path", "") or "subs").strip()
        sub_secret_path = derive_sub_server_path(sub_secret_raw)

        if not sub_host:
            log("[ERROR] Stage 3 failed: Subscription Server host address is required.", "error")
            return False, {}

        proxy_node_sub_base = ""
        if parsed_clients and parsed_clients[0].get("sub_url"):
            proxy_node_sub_base = parsed_clients[0]["sub_url"].rsplit("/", 1)[0]
        if not proxy_node_sub_base:
            proxy_node_sub_base = f"https://{proxy_host}/{derive_sub_path(proxy_secret)}"
        freedom_node_sub_base = ""
        if freedom_sub_url:
            freedom_node_sub_base = freedom_sub_url.rsplit("/", 1)[0]
        if not freedom_node_sub_base:
            freedom_node_sub_base = f"https://{freedom_host}/{derive_sub_path(freedom_secret)}"

        proxy_client_names = [n.strip() for n in re.split(r'[\s,]+', f"{proxy_clients_tcp_str} {proxy_clients_xhttp_str}") if n.strip()]
        freedom_client_names = [freedom_client]

        sub_admin_user = config.get("sub_admin_user", "").strip()
        sub_admin_password = config.get("sub_admin_password", "").strip()

        resolved_proxy, resolved_freedom, extra_sub_env = resolve_sub_server_urls(
            proxy_node_sub_base, freedom_node_sub_base,
        )
        ru_domain = config.get("proxy_domain") or config.get("proxy_host") or extract_domain_from_url(resolved_proxy)
        fr_domain = config.get("freedom_domain") or config.get("freedom_host") or extract_domain_from_url(resolved_freedom)

        sub_env = {
            "DOMAIN": sub_domain,
            "SECRET_SUB_PATH": sub_secret_path,
            "RUSSIAN_SUB_URL": resolved_proxy,
            "FOREIGN_SUB_URL": resolved_freedom,
            "PROXY_DOMAIN": ru_domain,
            "FREEDOM_DOMAIN": fr_domain,
            "PROXY_CLIENTS": " ".join(proxy_client_names),
            "FREEDOM_CLIENTS": " ".join(freedom_client_names),
            "ADMIN_USER": sub_admin_user,
            "ADMIN_PASSWORD": sub_admin_password,
            **extra_sub_env,
        }

        sub_decoy_files = prepare_decoy_files(config.get("sub_decoy_template") or config.get("decoy_template"), "Subscription Server")
        sub_target = sub_host
        effective_sub_port = updated_ssh_ports.get(sub_target, sub_port)
        ok3, out3 = await _deploy_sub_server(sub_target, effective_sub_port, sub_user, sub_password, sub_key, sub_env, log, cancel_check=cancel_check, bundle_source_dir=bundle_dir, decoy_files=sub_decoy_files)
        if not ok3:
            log("[ERROR] Stage 3 failed: Subscription Server deployment failed.", "error")
            return False, {}

        log("", "success")
        log("✅ [STAGE 3 COMPLETE] Subscription Server deployed successfully!", "success")
        log("", "success")

        if change_ssh_port and new_ssh_port:
            if await _change_remote_ssh_port(sub_target, effective_sub_port, new_ssh_port, sub_user, sub_password, sub_key, log, cancel_check):
                updated_ssh_ports[sub_host] = new_ssh_port
                if sub_domain and sub_domain != sub_host:
                    updated_ssh_ports[sub_domain] = new_ssh_port

        base_sub_url = f"https://{sub_domain}/{sub_secret_path}"
        result_data["sub_domain"] = sub_domain
        result_data["sub_secret_path"] = sub_secret_path
        result_data["sub_base_url"] = base_sub_url
        result_data["sub_admin_user"] = sub_admin_user
        result_data["sub_admin_password"] = sub_admin_password

        # Attach sub_url to client objects if available
        for cl in parsed_clients:
            cl["sub_server_url"] = f"{base_sub_url}/{cl['name']}"

    if updated_ssh_ports:
        result_data["new_ssh_port"] = new_ssh_port
        result_data["updated_ssh_ports"] = updated_ssh_ports

    log("╔════════════════════════════════════════════╗", "success")
    log("║         🎉 ALL STAGES COMPLETED! 🎉         ║", "success")
    log("╚════════════════════════════════════════════╝", "success")
    log("", "success")
    log(f"Panel 1 (Freedom Node): {freedom_final_xui_url}", "success")
    log(f"  - Admin User: {freedom_xui_user}", "success")
    log(f"  - Admin Password: ••••••••", "success")
    log(f"Panel 2 (Proxy Node): {final_xui_url}", "success")
    log(f"  - Admin User: {proxy_xui_user}", "success")
    log(f"  - Admin Password: ••••••••", "success")
    if deploy_mode == "cascade_sub":
        log(f"Subscription Server: https://{result_data['sub_domain']}/{result_data['sub_secret_path']}/<username>", "success")
        log(f"  - Admin: {result_data.get('sub_admin_user', 'admin')} / password: ••••••••", "success")
    log("=========================================", "success")
    return True, result_data