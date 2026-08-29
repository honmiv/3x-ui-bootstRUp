#!/usr/bin/env python3
"""
Test: Freedom Node + Subscription Server Deployment (deploy_mode: freedom_sub)
Spins up vps-freedomsub-freedom and vps-freedomsub-sub containers.
Executes automated 2-stage deployment:
  Stage 1: Freedom Node (Foreign VPS)
  Stage 2: Subscription Server (Centralized subscription manager with direct freedom backend)
Verifies both VPS nodes, TLS, and end-to-end subscription distribution.
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

FREEDOM_PORT = 2251
FREEDOM_DOMAIN = "freedomsub-freedom.test"
FREEDOM_CONTAINER = "vps-freedomsub-freedom"

SUB_PORT = 2252
SUB_DOMAIN = "freedomsub-sub.test"
SUB_CONTAINER = "vps-freedomsub-sub"
SECRET_SUB_PATH = "subs"


async def test_freedom_sub_deployment() -> bool:
    ensure_test_containers_running(FREEDOM_CONTAINER, SUB_CONTAINER)

    # Patch ssh_deployer resolvers for DinD networking before deployment.
    install_dind_overrides("", FREEDOM_CONTAINER)

    config = {
        "deploy_mode": "freedom_sub",

        # Freedom Node (Stage 1)
        "vps_host": FREEDOM_DOMAIN,
        "vps_host_for_ssh": "127.0.0.1",
        "vps_port": FREEDOM_PORT,
        "vps_user": "root",
        "vps_password": "root",
        "domain": FREEDOM_DOMAIN,
        "xui_username": "freedomadmin",
        "xui_password": "FreedomAdminPassword123!",
        "sub_secret": "freedom_sub_secret_key",
        "client_tcp_list": "client-freedom-tcp",
        "client_xhttp_list": "client-freedom-xhttp",
        "xui_version": "3.6.0",

        # Subscription Server (Stage 2)
        "sub_vps_host": "127.0.0.1",
        "sub_vps_port": SUB_PORT,
        "sub_vps_user": "root",
        "sub_vps_password": "root",
        "sub_domain": SUB_DOMAIN,
        "sub_secret_path": SECRET_SUB_PATH,
        "sub_admin_user": "subadmin",
        "sub_admin_password": "SubAdminMasterPass123!",

        "bundle_source_dir": prepare_test_repo("panel", "sub-server"),
    }

    log("Starting 2-Stage Freedom + Sub Deployment via ssh_deployer...", "info")
    ok, result = await run_deployment(config, log)

    if not ok:
        log("2-Stage Freedom + Sub deployment failed!", "error")
        return False

    log("2-Stage Freedom + Sub deployment returned success!", "success")
    log(f"Result details: {result}", "info")

    # 1. Verify Freedom Node
    if not check_inner_containers_running(FREEDOM_CONTAINER, ["3xui", "caddy", "nginx-decoy"]):
        return False

    # 2. Verify Subscription Server
    if not check_inner_containers_running(SUB_CONTAINER, ["subs-server", "sub-caddy", "sub-nginx-decoy"]):
        return False

    # 3. Verify TLS on both nodes via host --resolve (Caddy L4 end-to-end)
    f_sub_base = hashlib.md5(f"{config['sub_secret']}-sub".encode("utf-8")).hexdigest()[:16]

    tls_checks = [
        ("Freedom node (TCP)", FREEDOM_CONTAINER, FREEDOM_DOMAIN, f"{f_sub_base}/client-freedom-tcp"),
        ("Freedom node (XHTTP)", FREEDOM_CONTAINER, FREEDOM_DOMAIN, f"{f_sub_base}/client-freedom-xhttp"),
        ("Sub-Server (TCP)", SUB_CONTAINER, SUB_DOMAIN, f"{SECRET_SUB_PATH}/client-freedom-tcp"),
        ("Sub-Server (XHTTP)", SUB_CONTAINER, SUB_DOMAIN, f"{SECRET_SUB_PATH}/client-freedom-xhttp"),
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
    log("🎉 TEST 2-STAGE FREEDOM + SUB DEPLOYMENT PASSED! 🎉", "success")
    log("=========================================================", "success")
    return True


def main():
    ok = asyncio.run(test_freedom_sub_deployment())
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
