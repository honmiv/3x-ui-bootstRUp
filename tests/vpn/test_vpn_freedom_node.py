#!/usr/bin/env python3
"""
Test: Freedom Node Deployment + Subscription Fetch + VPN E2E Connectivity
Deploys Freedom Node, fetches subscription, spins up XRay client,
and verifies end-to-end VPN tunnel by reaching echo-server through the tunnel.
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

SSH_PORT = 2221
DOMAIN = "freedom-only.test"
CONTAINER_NAME = "vps-freedom-only"

XRAY_CLIENT_CONTAINER = "vps-test-client-freedom"
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
    # Wait for it to be ready
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


async def test_freedom_deployment() -> bool:
    ensure_test_containers_running(CONTAINER_NAME)
    ensure_echo_server_running()

    config = {
        "deploy_mode": "freedom_only",
        "vps_host": "127.0.0.1",
        "vps_port": SSH_PORT,
        "vps_user": "root",
        "vps_password": "root",
        "vps_auth_type": "password",
        "domain": DOMAIN,
        "xui_username": "admin",
        "xui_password": "FreedomAdminPassword123!",
        "xui_version": "3.6.0",
        "sub_secret": "freedom_test_secret_phrase",
        "freedom_client_name": "local-proxy-node-client",
        "client_xhttp_list": "local-proxy-node-client",
        "client_tcp_list": "freedom-direct-client",
        "bundle_source_dir": prepare_test_repo("panel"),
    }

    log("Starting Freedom Node deployment...", "info")
    ok, result = await run_deployment(config, log)

    if not ok:
        log("Freedom Node deployment failed!", "error")
        return False

    log(f"Result: {result}", "success")

    # ── Fetch & decode subscription ──
    sub_secret = config["sub_secret"]
    sub_base_path = hashlib.md5(f"{sub_secret}-sub".encode("utf-8")).hexdigest()[:16]

    # Use the TCP client (not xhttp) because Caddy L4 on :443 proxies
    # all raw TCP to the TCP Reality inbound (port 61617). The xhttp
    # inbound (port 51843) is not reachable through Caddy's L4 layer.
    tcp_path = f"{sub_base_path}/freedom-direct-client"
    log(f"Fetching TCP subscription: {tcp_path}...", "info")
    status, body = fetch_subscription_via_host_tls(CONTAINER_NAME, DOMAIN, tcp_path)
    links = decode_vless_subscription(body)
    log(f"TCP subscription: status={status}, links={len(links) if links else 0}", "info")
    if not links:
        log("No subscription links returned — cannot test VPN connectivity.", "error")
        return False

    vless_url = links[0]
    log(f"TCP vless: {vless_url[:100]}...", "info")

    # ── Parse subscription & build XRay client config ──
    vless_data = parse_vless_url(vless_url)
    log(f"Parsed VLESS: server={vless_data['address']}:{vless_data['port']} "
        f"type={vless_data['type']} sni={vless_data['sni']}", "info")

    xray_config = generate_xray_client_config(vless_data, socks_port=XRAY_SOCKS_PORT)
    log("Generated XRay client config.", "info")

    # ── Start XRay client container on testnet ──
    ok = start_xray_test_client(xray_config, XRAY_CLIENT_CONTAINER)
    if not ok:
        log("XRay client failed to start!", "error")
        return False

    passed = False
    try:
        # ── VPN connectivity: curl through tunnel → echo-server ──
        log(f"Querying echo server through VPN tunnel ({ECHO_TEST_URL})...", "info")
        echo_data = query_echo_server_via_vpn(
            runner_container=CONTAINER_NAME,
            proxy_client_name=XRAY_CLIENT_CONTAINER,
            socks_port=XRAY_SOCKS_PORT,
            target_url=ECHO_TEST_URL,
        )
        log(f"Echo response: {echo_data}", "info")

        if not echo_data:
            log("VPN connectivity test FAILED — no response from echo server.", "error")
            return False

        # ── Verify egress IP ──
        # Traffic: xray_client → VPN tunnel → freedom_node → echo_server
        # Echo server sees connection from freedom node's IP on testnet.
        expected_egress_ip = get_container_ip(CONTAINER_NAME)
        actual_client_ip = echo_data.get("client_ip", "")
        log(f"Egress check: echo saw client_ip={actual_client_ip}, "
            f"expected freedom_node IP={expected_egress_ip}", "info")

        if actual_client_ip == expected_egress_ip:
            log("VPN E2E test PASSED — traffic egressed through freedom node.", "success")
            passed = True
        else:
            log(f"VPN E2E test FAILED — egress IP mismatch "
                f"(got {actual_client_ip}, expected {expected_egress_ip}).", "error")

    finally:
        stop_xray_test_client(XRAY_CLIENT_CONTAINER)

    return passed


def main():
    ok = asyncio.run(test_freedom_deployment())
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
