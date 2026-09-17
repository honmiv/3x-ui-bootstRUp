#!/usr/bin/env python3
"""
Test: Two-Node Cascade Deployment + Subscription Fetch + VPN E2E Connectivity
Deploys Freedom + Proxy nodes, validates all subscriptions via host TLS,
spins up an XRay client connecting to the Proxy node, and verifies
end-to-end traffic egresses via the Freedom node to echo-server.
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

FREEDOM_PORT = 2231
FREEDOM_DOMAIN = "cascade-freedom.test"
FREEDOM_CONTAINER = "vps-cascade-freedom"

PROXY_PORT = 2232
PROXY_DOMAIN = "cascade-proxy.test"
PROXY_CONTAINER = "vps-cascade-proxy"

XRAY_CLIENT_CONTAINER = "vps-test-client-cascade"
XRAY_SOCKS_PORT = 10808
ECHO_SERVER_CONTAINER = "echo-server"
ECHO_TEST_URL = "http://echo.test/ip"


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
            log("Echo server started.", "success")
            return
        time.sleep(1)
    log("Echo server failed to start!", "error")


async def test_cascade_deployment() -> bool:
    ensure_test_containers_running(FREEDOM_CONTAINER, PROXY_CONTAINER)
    ensure_echo_server_running()

    config = {
        "deploy_mode": "cascade",
        "is_cascade": True,
        "freedom_host": FREEDOM_DOMAIN,
        "freedom_host_for_ssh": "127.0.0.1",
        "freedom_port": FREEDOM_PORT,
        "freedom_user": "root",
        "freedom_password": "root",
        "freedom_domain": FREEDOM_DOMAIN,
        "freedom_xui_username": "freedomadmin",
        "freedom_xui_password": "FreedomAdminPassword123!",
        "freedom_sub_secret": "freedom_cascade_secret_key",
        "freedom_client_name": "local-proxy-node-client",
        "freedom_xui_version": "3.6.0",

        "proxy_host": PROXY_DOMAIN,
        "proxy_host_for_ssh": "127.0.0.1",
        "proxy_port": PROXY_PORT,
        "proxy_user": "root",
        "proxy_password": "root",
        "proxy_domain": PROXY_DOMAIN,
        "proxy_xui_username": "proxyadmin",
        "proxy_xui_password": "ProxyAdminPassword123!",
        "proxy_sub_secret": "proxy_cascade_secret_key",
        "proxy_client_tcp_list": "cascade-user-tcp",
        "proxy_client_xhttp_list": "cascade-user-xhttp",
        "proxy_xui_version": "3.6.0",

        "bundle_source_dir": prepare_test_repo("panel"),
    }

    log("Starting 2-Stage Cascade Deployment...", "info")
    ok, result = await run_deployment(config, log)

    if not ok:
        log("Cascade deployment failed!", "error")
        return False

    log(f"Result: {result}", "success")

    f_sub_base = hashlib.md5(f"{config['freedom_sub_secret']}-sub".encode("utf-8")).hexdigest()[:16]
    p_sub_base = hashlib.md5(f"{config['proxy_sub_secret']}-sub".encode("utf-8")).hexdigest()[:16]

    proxy_tcp_vless = ""
    for label, container, domain, path in [
        ("Freedom", FREEDOM_CONTAINER, FREEDOM_DOMAIN, f"{f_sub_base}/local-proxy-node-client"),
        ("Proxy TCP", PROXY_CONTAINER, PROXY_DOMAIN, f"{p_sub_base}/cascade-user-tcp"),
        ("Proxy XHTTP", PROXY_CONTAINER, PROXY_DOMAIN, f"{p_sub_base}/cascade-user-xhttp"),
    ]:
        log(f"Fetching {label} subscription: {path}...", "info")
        status, body = fetch_subscription_via_host_tls(container, domain, path)
        if status != 200:
            log(f"{label} subscription request failed: status={status}", "error")
            return False
        links = decode_vless_subscription(body)
        if not links:
            log(f"{label} subscription returned no valid VLESS links!", "error")
            return False
        log(f"{label}: status={status}, links={len(links)}", "info")
        if label == "Proxy TCP":
            proxy_tcp_vless = links[0]

    # ── Parse subscription & build XRay client config for Proxy TCP ──
    log(f"Proxy TCP VLESS link: {proxy_tcp_vless[:80]}...", "info")
    vless_data = parse_vless_url(proxy_tcp_vless)
    xray_config = generate_xray_client_config(vless_data, socks_port=XRAY_SOCKS_PORT)

    ok = start_xray_test_client(xray_config, XRAY_CLIENT_CONTAINER)
    if not ok:
        log("XRay client failed to start!", "error")
        return False

    passed = False
    try:
        log(f"Querying echo server through Cascade tunnel ({ECHO_TEST_URL})...", "info")
        echo_data = query_echo_server_via_vpn(
            runner_container=PROXY_CONTAINER,
            proxy_client_name=XRAY_CLIENT_CONTAINER,
            socks_port=XRAY_SOCKS_PORT,
            target_url=ECHO_TEST_URL,
        )
        log(f"Echo response: {echo_data}", "info")
        if not echo_data:
            log("Cascade VPN connectivity test FAILED — no response from echo server.", "error")
            return False

        # In a cascade setup: client -> proxy node -> freedom node -> internet/echo
        # Traffic egresses from the Freedom node's container IP on testnet
        expected_egress_ip = get_container_ip(FREEDOM_CONTAINER)
        actual_client_ip = echo_data.get("client_ip", "")
        log(f"Egress check: echo saw client_ip={actual_client_ip}, "
            f"expected freedom_node IP={expected_egress_ip}", "info")

        if actual_client_ip == expected_egress_ip:
            log("Cascade VPN E2E test PASSED — traffic egressed through freedom node!", "success")
            passed = True
        else:
            log(f"Cascade VPN E2E test FAILED — egress IP mismatch "
                f"(got {actual_client_ip}, expected {expected_egress_ip}).", "error")
    finally:
        stop_xray_test_client(XRAY_CLIENT_CONTAINER)

    return passed


def main():
    ok = asyncio.run(test_cascade_deployment())
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
