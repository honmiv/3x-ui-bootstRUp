#!/usr/bin/env python3
"""
Test: Freedom + Sub-Server Deployment + Subscription Fetch + VPN E2E Connectivity
Deploys Freedom Node and Sub-Server, fetches subscription from Sub-Server via host TLS,
starts an XRay test client, and verifies end-to-end VPN tunneling to echo-server.
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
    decode_vless_subscription,
    ensure_test_containers_running,
    fetch_subscription_via_host_tls,
    get_container_ip,
    generate_xray_client_config,
    parse_vless_url,
    start_xray_test_client,
    stop_xray_test_client,
    query_echo_server_via_vpn,
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

XRAY_CLIENT_CONTAINER = "vps-test-client-freedomsub"
XRAY_SOCKS_PORT = 10808
ECHO_SERVER_CONTAINER = "echo-server"
ECHO_TEST_HOST = "echo.test"
ECHO_TEST_URL = f"http://{ECHO_TEST_HOST}/ip"


def ensure_echo_server_running():
    """Ensure the shared echo-server Docker Compose service is up."""
    res = subprocess.run(
        ["docker", "inspect", "-f", "{{.State.Running}}", ECHO_SERVER_CONTAINER],
        capture_output=True, text=True,
    )
    if res.stdout.strip() == "true":
        log(f"Echo server {ECHO_SERVER_CONTAINER} already running.", "success")
        return

    log(f"Starting echo server {ECHO_SERVER_CONTAINER}...", "info")
    compose_file = os.path.join(REPO_ROOT, "tests", "docker-compose.test.yml")
    subprocess.run(
        ["docker", "compose", "-f", compose_file, "up", "-d", ECHO_SERVER_CONTAINER],
        cwd=os.path.join(REPO_ROOT, "tests"),
        capture_output=True, text=True,
    )
    for _ in range(15):
        res = subprocess.run(
            ["docker", "inspect", "-f", "{{.State.Running}}", ECHO_SERVER_CONTAINER],
            capture_output=True, text=True,
        )
        if res.stdout.strip() == "true":
            log(f"Echo server started.", "success")
            return
        time.sleep(1)
    log(f"Echo server failed to start!", "error")


async def test_freedom_sub_vpn() -> bool:
    ensure_test_containers_running(FREEDOM_CONTAINER, SUB_CONTAINER)
    ensure_echo_server_running()

    # Patch resolvers for DinD test networking
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

    log("Starting 2-Stage Freedom + Sub Deployment...", "info")
    ok, result = await run_deployment(config, log)

    if not ok:
        log("Freedom + Sub deployment failed!", "error")
        return False

    log(f"Deployment result: {result}", "success")

    # Fetch TCP client subscription from Sub-Server via host TLS
    sub_path = f"{SECRET_SUB_PATH}/client-freedom-tcp"
    log(f"Fetching subscription from Sub-Server: {sub_path}...", "info")
    status, body = fetch_subscription_via_host_tls(SUB_CONTAINER, SUB_DOMAIN, sub_path)
    links = decode_vless_subscription(body)
    log(f"Subscription: status={status}, links={len(links) if links else 0}", "info")
    if not links:
        log("No subscription links returned from Sub-Server!", "error")
        return False

    vless_url = links[0]
    log(f"VLESS URL: {vless_url[:100]}...", "info")

    # Parse subscription & build XRay client config
    vless_data = parse_vless_url(vless_url)
    log(f"Parsed VLESS: server={vless_data['address']}:{vless_data['port']} "
        f"type={vless_data['type']} sni={vless_data['sni']}", "info")

    xray_config = generate_xray_client_config(vless_data, socks_port=XRAY_SOCKS_PORT)
    log("Generated XRay client config.", "info")

    # Start XRay client container on testnet
    ok = start_xray_test_client(xray_config, XRAY_CLIENT_CONTAINER)
    if not ok:
        log("XRay client failed to start!", "error")
        return False

    passed = False
    try:
        log(f"Querying echo server through VPN tunnel ({ECHO_TEST_URL})...", "info")
        echo_data = query_echo_server_via_vpn(
            runner_container=SUB_CONTAINER,
            proxy_client_name=XRAY_CLIENT_CONTAINER,
            socks_port=XRAY_SOCKS_PORT,
            target_url=ECHO_TEST_URL,
        )
        log(f"Echo response: {echo_data}", "info")

        if not echo_data:
            log("VPN connectivity test FAILED — no response from echo server.", "error")
            return False

        expected_egress_ip = get_container_ip(FREEDOM_CONTAINER)
        actual_client_ip = echo_data.get("client_ip", "")
        log(f"Egress check: echo saw client_ip={actual_client_ip}, "
            f"expected freedom_node IP={expected_egress_ip}", "info")

        if actual_client_ip == expected_egress_ip:
            log("VPN E2E test PASSED — traffic egressed through freedom node via Sub-Server subscription!", "success")
            passed = True
        else:
            log(f"VPN E2E test FAILED — egress IP mismatch "
                f"(got {actual_client_ip}, expected {expected_egress_ip}).", "error")

    finally:
        stop_xray_test_client(XRAY_CLIENT_CONTAINER)

    return passed


def main():
    ok = asyncio.run(test_freedom_sub_vpn())
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
