#!/usr/bin/env python3
"""
Test: Full Cascade + Subscription Server Deployment (deploy_mode: cascade_sub)
Spins up vps-cascadesub-freedom, vps-cascadesub-proxy, and vps-cascadesub-sub containers.
Executes automated 3-stage deployment:
  Stage 1: Freedom Node (Foreign VPS)
  Stage 2: Proxy Node (Domestic VPS with outbound sub to Freedom Node)
  Stage 3: Subscription Server (Centralized subscription manager)
Verifies all 3 VPS nodes, TLS, and end-to-end subscription distribution.
"""

import asyncio
import hashlib
import os
import sys

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from ssh_deployer import run_deployment
from tests.helpers import (
    prepare_test_repo,
    check_inner_containers_running,
    decode_vless_subscription,
    ensure_test_containers_running,
    fetch_subscription_via_host_tls,
    log,
)
from tests.overrides.ssh_deployer_test_overrides import install_dind_overrides

FREEDOM_PORT = 2241
FREEDOM_DOMAIN = "cascadesub-freedom.test"
FREEDOM_CONTAINER = "vps-cascadesub-freedom"

PROXY_PORT = 2242
PROXY_DOMAIN = "cascadesub-proxy.test"
PROXY_CONTAINER = "vps-cascadesub-proxy"

SUB_PORT = 2243
SUB_DOMAIN = "cascadesub-sub.test"
SUB_CONTAINER = "vps-cascadesub-sub"
SECRET_SUB_PATH = "subs"


async def test_cascade_sub_deployment() -> bool:
    ensure_test_containers_running(FREEDOM_CONTAINER, PROXY_CONTAINER, SUB_CONTAINER)

    # Patch ssh_deployer resolvers for DinD networking before deployment.
    install_dind_overrides(PROXY_CONTAINER, FREEDOM_CONTAINER)

    config = {
        "deploy_mode": "cascade_sub",
        "is_cascade": True,

        # Freedom Node (Stage 1)
        "freedom_host": FREEDOM_DOMAIN,
        "freedom_host_for_ssh": "127.0.0.1",
        "freedom_port": FREEDOM_PORT,
        "freedom_user": "root",
        "freedom_password": "root",
        "freedom_domain": FREEDOM_DOMAIN,
        "freedom_xui_username": "freedomadmin",
        "freedom_xui_password": "FreedomAdminPassword123!",
        "freedom_sub_secret": "freedom_cascade_secret_sub_key",
        "freedom_client_name": "local-proxy-node-client",
        "freedom_xui_version": "3.6.0",

        # Proxy Node (Stage 2)
        "proxy_host": PROXY_DOMAIN,
        "proxy_host_for_ssh": "127.0.0.1",
        "proxy_port": PROXY_PORT,
        "proxy_user": "root",
        "proxy_password": "root",
        "proxy_domain": PROXY_DOMAIN,
        "proxy_xui_username": "proxyadmin",
        "proxy_xui_password": "ProxyAdminPassword123!",
        "proxy_sub_secret": "proxy_cascade_secret_sub_key",
        "proxy_client_tcp_list": "client-cascade-tcp",
        "proxy_client_xhttp_list": "client-cascade-xhttp",
        "proxy_xui_version": "3.6.0",

        # Subscription Server (Stage 3)
        "sub_vps_host": "127.0.0.1",
        "sub_vps_port": SUB_PORT,
        "sub_vps_user": "root",
        "sub_vps_password": "root",
        "sub_domain": SUB_DOMAIN,
        "sub_secret_path": SECRET_SUB_PATH,
        "sub_proxy_clients": "client-cascade-tcp, client-cascade-xhttp",
        "sub_freedom_clients": "",
        "sub_admin_user": "subadmin",
        "sub_admin_password": "SubAdminMasterPass123!",

        "bundle_source_dir": prepare_test_repo("panel", "sub-server"),
    }

    log("Starting 3-Stage Cascade + Sub Deployment via ssh_deployer...", "info")
    ok, result = await run_deployment(config, log)

    if not ok:
        log("3-Stage Cascade + Sub deployment failed!", "error")
        return False

    log("3-Stage Cascade + Sub deployment returned success!", "success")
    log(f"Result details: {result}", "info")

    # 1. Verify Freedom Node
    if not check_inner_containers_running(FREEDOM_CONTAINER, ["3xui", "caddy", "nginx-decoy"]):
        return False

    # 2. Verify Proxy Node
    if not check_inner_containers_running(PROXY_CONTAINER, ["3xui", "caddy", "nginx-decoy"]):
        return False

    # 3. Verify Subscription Server
    if not check_inner_containers_running(SUB_CONTAINER, ["subs-server", "sub-caddy", "sub-nginx-decoy"]):
        return False

    # 4. Verify TLS on all 3 nodes via host --resolve (Caddy L4 end-to-end)
    f_sub_base = hashlib.md5(f"{config['freedom_sub_secret']}-sub".encode("utf-8")).hexdigest()[:16]
    p_sub_base = hashlib.md5(f"{config['proxy_sub_secret']}-sub".encode("utf-8")).hexdigest()[:16]

    tls_checks = [
        ("Proxy node", PROXY_CONTAINER, PROXY_DOMAIN, f"{p_sub_base}/client-cascade-tcp"),
        ("Proxy node", PROXY_CONTAINER, PROXY_DOMAIN, f"{p_sub_base}/client-cascade-xhttp"),
        ("Freedom node", FREEDOM_CONTAINER, FREEDOM_DOMAIN, f"{f_sub_base}/local-proxy-node-client"),
        ("Sub-Server", SUB_CONTAINER, SUB_DOMAIN, f"{SECRET_SUB_PATH}/client-cascade-tcp"),
        ("Sub-Server", SUB_CONTAINER, SUB_DOMAIN, f"{SECRET_SUB_PATH}/client-cascade-xhttp"),
        ("Sub-Server", SUB_CONTAINER, SUB_DOMAIN, f"{SECRET_SUB_PATH}/local-proxy-node-client"),
    ]
    for label, container, domain, path in tls_checks:
        tls_status, tls_body = fetch_subscription_via_host_tls(container, domain, path)
        if tls_status != 200:
            log(f"TLS check FAILED for {label}: HTTP {tls_status}", "error")
            return False
        tls_links = decode_vless_subscription(tls_body)
        if not tls_links:
            log(f"TLS check FAILED for {label}: HTTP 200 but base64 decode failed", "error")
            return False
        log(f"TLS check OK for {label} ({len(tls_links)} link(s) via Caddy L4)", "success")
    log("=========================================================", "success")
    log("🎉 TEST 3-STAGE CASCADE + SUB DEPLOYMENT PASSED! 🎉", "success")
    log("=========================================================", "success")
    return True


def main():
    ok = asyncio.run(test_cascade_sub_deployment())
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
