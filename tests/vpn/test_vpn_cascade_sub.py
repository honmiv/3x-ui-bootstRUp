#!/usr/bin/env python3
"""
Test: 3-Stage Cascade + Subscription Server Deployment + Subscription Fetch + VPN E2E Connectivity
Deploys Freedom, Proxy, and Sub-Server nodes, validates all subscriptions via host TLS,
spins up an XRay client using the Sub-Server delivered profile, and verifies
end-to-end traffic egresses through Freedom node to echo-server.
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

XRAY_CLIENT_CONTAINER = "vps-test-client-cascadesub"
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


async def test_cascade_sub_deployment() -> bool:
    ensure_test_containers_running(FREEDOM_CONTAINER, PROXY_CONTAINER, SUB_CONTAINER)
    ensure_echo_server_running()

    install_dind_overrides(PROXY_CONTAINER, FREEDOM_CONTAINER)

    config = {
        "deploy_mode": "cascade_sub",
        "is_cascade": True,

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

    log("Starting 3-Stage Cascade + Sub Deployment...", "info")
    ok, result = await run_deployment(config, log)

    if not ok:
        log("Deployment failed!", "error")
        return False

    log(f"Result: {result}", "success")

    f_sub_base = hashlib.md5(f"{config['freedom_sub_secret']}-sub".encode("utf-8")).hexdigest()[:16]
    p_sub_base = hashlib.md5(f"{config['proxy_sub_secret']}-sub".encode("utf-8")).hexdigest()[:16]
    s_sub_base = hashlib.md5(config['sub_secret_path'].encode("utf-8")).hexdigest()[:16]

    checks = [
        ("Freedom", FREEDOM_CONTAINER, FREEDOM_DOMAIN, f"{f_sub_base}/local-proxy-node-client"),
        ("Proxy TCP", PROXY_CONTAINER, PROXY_DOMAIN, f"{p_sub_base}/client-cascade-tcp"),
        ("Proxy XHTTP", PROXY_CONTAINER, PROXY_DOMAIN, f"{p_sub_base}/client-cascade-xhttp"),
        ("Sub TCP", SUB_CONTAINER, SUB_DOMAIN, f"{s_sub_base}/client-cascade-tcp"),
        ("Sub XHTTP", SUB_CONTAINER, SUB_DOMAIN, f"{s_sub_base}/client-cascade-xhttp"),
        ("Sub LocalProxy", SUB_CONTAINER, SUB_DOMAIN, f"{s_sub_base}/local-proxy-node-client"),
    ]

    sub_tcp_vless = ""
    for label, container, domain, path in checks:
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
        if label == "Sub TCP":
            sub_tcp_vless = links[0]

    # ── Parse Sub-Server delivered TCP profile & build XRay client config ──
    log(f"Sub TCP VLESS link: {sub_tcp_vless[:80]}...", "info")
    vless_data = parse_vless_url(sub_tcp_vless)
    xray_config = generate_xray_client_config(vless_data, socks_port=XRAY_SOCKS_PORT)

    ok = start_xray_test_client(xray_config, XRAY_CLIENT_CONTAINER)
    if not ok:
        log("XRay client failed to start!", "error")
        return False

    passed = False
    try:
        log(f"Querying echo server through 3-Stage Cascade + Sub tunnel ({ECHO_TEST_URL})...", "info")
        echo_data = query_echo_server_via_vpn(
            runner_container=SUB_CONTAINER,
            proxy_client_name=XRAY_CLIENT_CONTAINER,
            socks_port=XRAY_SOCKS_PORT,
            target_url=ECHO_TEST_URL,
        )
        log(f"Echo response: {echo_data}", "info")
        if not echo_data:
            log("Cascade + Sub VPN connectivity test FAILED — no response from echo server.", "error")
            return False

        # In 3-stage cascade: client -> proxy node -> freedom node -> echo-server
        # Egress IP is the Freedom node's container IP on testnet
        expected_egress_ip = get_container_ip(FREEDOM_CONTAINER)
        actual_client_ip = echo_data.get("client_ip", "")
        log(f"Egress check: echo saw client_ip={actual_client_ip}, "
            f"expected freedom_node IP={expected_egress_ip}", "info")

        if actual_client_ip == expected_egress_ip:
            log("Cascade + Sub VPN E2E test PASSED — traffic egressed through freedom node!", "success")
            passed = True
        else:
            log(f"Cascade + Sub VPN E2E test FAILED — egress IP mismatch "
                f"(got {actual_client_ip}, expected {expected_egress_ip}).", "error")
    finally:
        stop_xray_test_client(XRAY_CLIENT_CONTAINER)

    return passed


def main():
    ok = asyncio.run(test_cascade_sub_deployment())
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
