#!/usr/bin/env python3
"""
Test: Proxy Node Deployment + Subscription Fetch + VPN E2E Connectivity
Deploys Foreign Backend + Proxy Node, validates subscriptions via host TLS,
spins up an XRay client connecting to the Proxy Node, and verifies
end-to-end traffic egresses via the Foreign Backend node to echo-server.
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

SSH_PORT = 2222
DOMAIN = "proxy-only.test"
CONTAINER_NAME = "vps-proxy-only"

FOREIGN_SSH_PORT = 2225
FOREIGN_DOMAIN = "proxy-foreign.test"
FOREIGN_CONTAINER = "vps-proxy-foreign"

XRAY_CLIENT_CONTAINER = "vps-test-client-proxy"
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


async def ensure_foreign_node_deployed() -> str:
    ensure_test_containers_running(FOREIGN_CONTAINER)
    foreign_sub_secret = "proxy_foreign_secret_phrase"
    sub_base_path = hashlib.md5(f"{foreign_sub_secret}-sub".encode("utf-8")).hexdigest()[:16]
    foreign_sub_url = f"https://{FOREIGN_DOMAIN}/{sub_base_path}/local-proxy-node-client"

    config_foreign = {
        "deploy_mode": "freedom_only",
        "vps_host": "127.0.0.1",
        "vps_port": FOREIGN_SSH_PORT,
        "vps_user": "root",
        "vps_password": "root",
        "vps_auth_type": "password",
        "domain": FOREIGN_DOMAIN,
        "xui_username": "admin",
        "xui_password": "ForeignAdminPassword123!",
        "xui_version": "3.6.0",
        "sub_secret": foreign_sub_secret,
        "freedom_client_name": "local-proxy-node-client",
        "client_xhttp_list": "local-proxy-node-client",
        "client_tcp_list": "freedom-direct-client",
        "bundle_source_dir": prepare_test_repo("panel"),
    }
    log(f"Deploying foreign backend node on {FOREIGN_CONTAINER}...", "info")
    ok, res = await run_deployment(config_foreign, log)
    if not ok:
        log(f"Foreign node deployment failed on {FOREIGN_CONTAINER}!", "error")

    return foreign_sub_url


async def test_proxy_deployment() -> bool:
    ensure_test_containers_running(CONTAINER_NAME)
    ensure_echo_server_running()
    foreign_sub_url = await ensure_foreign_node_deployed()

    config = {
        "deploy_mode": "proxy_only",
        "vps_host": "127.0.0.1",
        "vps_port": SSH_PORT,
        "vps_user": "root",
        "vps_password": "root",
        "vps_auth_type": "password",
        "domain": DOMAIN,
        "xui_username": "admin",
        "xui_password": "ProxyAdminPassword123!",
        "xui_version": "3.6.0",
        "sub_secret": "proxy_test_secret_phrase",
        "foreign_sub_url": foreign_sub_url,
        "client_xhttp_list": "proxy-user-xhttp",
        "client_tcp_list": "proxy-user-tcp",
        "bundle_source_dir": prepare_test_repo("panel"),
    }

    log(f"Starting Proxy Node deployment on {CONTAINER_NAME}...", "info")
    ok, result = await run_deployment(config, log)

    if not ok:
        log("Proxy Node deployment failed!", "error")
        return False

    log(f"Result: {result}", "success")

    sub_secret = config["sub_secret"]
    sub_base_path = hashlib.md5(f"{sub_secret}-sub".encode("utf-8")).hexdigest()[:16]

    proxy_tcp_vless = ""
    for label, path in [("TCP", "proxy-user-tcp"), ("XHTTP", "proxy-user-xhttp")]:
        sub_path = f"{sub_base_path}/{path}"
        log(f"Fetching {label} subscription: {sub_path}...", "info")
        status, body = fetch_subscription_via_host_tls(CONTAINER_NAME, DOMAIN, sub_path)
        if status != 200:
            log(f"{label} subscription request failed: status={status}", "error")
            return False
        links = decode_vless_subscription(body)
        if not links:
            log(f"{label} subscription returned no valid VLESS links!", "error")
            return False
        log(f"{label} subscription: status={status}, links={len(links)}", "info")
        if label == "TCP":
            proxy_tcp_vless = links[0]

    # ── Parse subscription & build XRay client config ──
    log(f"Proxy TCP VLESS link: {proxy_tcp_vless[:80]}...", "info")
    vless_data = parse_vless_url(proxy_tcp_vless)
    xray_config = generate_xray_client_config(vless_data, socks_port=XRAY_SOCKS_PORT)

    ok = start_xray_test_client(xray_config, XRAY_CLIENT_CONTAINER)
    if not ok:
        log("XRay client failed to start!", "error")
        return False

    passed = False
    try:
        log(f"Querying echo server through Proxy Node tunnel ({ECHO_TEST_URL})...", "info")
        echo_data = query_echo_server_via_vpn(
            runner_container=CONTAINER_NAME,
            proxy_client_name=XRAY_CLIENT_CONTAINER,
            socks_port=XRAY_SOCKS_PORT,
            target_url=ECHO_TEST_URL,
        )
        log(f"Echo response: {echo_data}", "info")
        if not echo_data:
            log("Proxy VPN connectivity test FAILED — no response from echo server.", "error")
            return False

        # In a proxy setup: client -> proxy node -> foreign node -> internet/echo
        # Traffic egresses from the Foreign node's container IP on testnet
        expected_egress_ip = get_container_ip(FOREIGN_CONTAINER)
        actual_client_ip = echo_data.get("client_ip", "")
        log(f"Egress check: echo saw client_ip={actual_client_ip}, "
            f"expected foreign_node IP={expected_egress_ip}", "info")

        if actual_client_ip == expected_egress_ip:
            log("Proxy VPN E2E test PASSED — traffic egressed through foreign node!", "success")
            passed = True
        else:
            log(f"Proxy VPN E2E test FAILED — egress IP mismatch "
                f"(got {actual_client_ip}, expected {expected_egress_ip}).", "error")
    finally:
        stop_xray_test_client(XRAY_CLIENT_CONTAINER)

    return passed


def main():
    ok = asyncio.run(test_proxy_deployment())
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
