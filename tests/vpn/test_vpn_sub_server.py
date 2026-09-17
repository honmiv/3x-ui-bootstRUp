#!/usr/bin/env python3
"""
Test: Subscription Server Deployment + Subscription Fetch + VPN E2E Connectivity
Deploys Foreign Backend + Sub-Server, fetches client subscription via host TLS,
spins up an XRay client, and verifies end-to-end VPN tunneling to echo-server.
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

SSH_PORT = 2223
DOMAIN = "sub-only.test"
CONTAINER_NAME = "vps-sub-only"
SECRET_SUB_PATH = "subs"

FOREIGN_PORT = 2226
FOREIGN_DOMAIN = "sub-foreign.test"
FOREIGN_CONTAINER = "vps-sub-foreign"
FOREIGN_SUB_SECRET = "sub_foreign_secret_phrase"

XRAY_CLIENT_CONTAINER = "vps-test-client-sub"
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
    sub_base_path = hashlib.md5(f"{FOREIGN_SUB_SECRET}-sub".encode("utf-8")).hexdigest()[:16]
    foreign_sub_url = f"https://{FOREIGN_DOMAIN}/{sub_base_path}"

    config_foreign = {
        "deploy_mode": "freedom_only",
        "vps_host": "127.0.0.1",
        "vps_port": FOREIGN_PORT,
        "vps_user": "root",
        "vps_password": "root",
        "vps_auth_type": "password",
        "domain": FOREIGN_DOMAIN,
        "xui_username": "admin",
        "xui_password": "ForeignAdminPassword123!",
        "xui_version": "3.6.0",
        "sub_secret": FOREIGN_SUB_SECRET,
        "freedom_client_name": "freedom-direct",
        "client_tcp_list": "freedom-direct",
        "client_xhttp_list": "freedom-direct",
        "bundle_source_dir": prepare_test_repo("panel"),
    }
    log(f"Deploying foreign backend node on {FOREIGN_CONTAINER}...", "info")
    ok, res = await run_deployment(config_foreign, log)
    if not ok:
        log(f"Foreign node deployment failed on {FOREIGN_CONTAINER}!", "error")
        return ""
    return foreign_sub_url


async def test_sub_server_deployment() -> bool:
    ensure_test_containers_running(CONTAINER_NAME)
    ensure_echo_server_running()

    # Monkey-patch sub-server resolver for DinD networking
    install_dind_overrides("", FOREIGN_CONTAINER)

    foreign_sub_url = await ensure_foreign_node_deployed()
    if not foreign_sub_url:
        return False

    config = {
        "deploy_mode": "sub_only",
        "sub_vps_host": "127.0.0.1",
        "sub_vps_port": SSH_PORT,
        "sub_vps_user": "root",
        "sub_vps_password": "root",
        "sub_domain": DOMAIN,
        "sub_secret_path": SECRET_SUB_PATH,
        "sub_russian_url": "",
        "sub_foreign_url": foreign_sub_url,
        "sub_proxy_clients": "",
        "sub_freedom_clients": "freedom-direct",
        "sub_admin_user": "subadmin",
        "sub_admin_password": "SubAdminPassword123!",
        "bundle_source_dir": prepare_test_repo("panel", "sub-server"),
    }

    log(f"Starting Sub-Server deployment on {CONTAINER_NAME}...", "info")
    ok, result = await run_deployment(config, log)

    if not ok:
        log("Sub-Server deployment failed!", "error")
        return False

    log(f"Result: {result}", "success")

    s_sub_base = hashlib.md5(config['sub_secret_path'].encode("utf-8")).hexdigest()[:16]
    path = f"{s_sub_base}/freedom-direct"

    log(f"Fetching subscription for 'freedom-direct': {path}...", "info")
    status, body = fetch_subscription_via_host_tls(CONTAINER_NAME, DOMAIN, path)
    if status != 200:
        log(f"Sub-Server subscription request failed: status={status}", "error")
        return False
    links = decode_vless_subscription(body)
    if not links:
        log("Sub-Server returned no valid VLESS links!", "error")
        return False
    log(f"freedom-direct: status={status}, links={len(links)}", "info")

    vless_url = links[0]
    log(f"freedom-direct VLESS link: {vless_url[:80]}...", "info")
    vless_data = parse_vless_url(vless_url)
    xray_config = generate_xray_client_config(vless_data, socks_port=XRAY_SOCKS_PORT)

    ok = start_xray_test_client(xray_config, XRAY_CLIENT_CONTAINER)
    if not ok:
        log("XRay client failed to start!", "error")
        return False

    passed = False
    try:
        log(f"Querying echo server through Sub-Server provisioned VPN tunnel ({ECHO_TEST_URL})...", "info")
        echo_data = query_echo_server_via_vpn(
            runner_container=CONTAINER_NAME,
            proxy_client_name=XRAY_CLIENT_CONTAINER,
            socks_port=XRAY_SOCKS_PORT,
            target_url=ECHO_TEST_URL,
        )
        log(f"Echo response: {echo_data}", "info")
        if not echo_data:
            log("Sub-Server VPN connectivity test FAILED — no response from echo server.", "error")
            return False

        expected_egress_ip = get_container_ip(FOREIGN_CONTAINER)
        actual_client_ip = echo_data.get("client_ip", "")
        log(f"Egress check: echo saw client_ip={actual_client_ip}, "
            f"expected foreign_node IP={expected_egress_ip}", "info")

        if actual_client_ip == expected_egress_ip:
            log("Sub-Server VPN E2E test PASSED — traffic egressed through foreign node!", "success")
            passed = True
        else:
            log(f"Sub-Server VPN E2E test FAILED — egress IP mismatch "
                f"(got {actual_client_ip}, expected {expected_egress_ip}).", "error")
    finally:
        stop_xray_test_client(XRAY_CLIENT_CONTAINER)

    return passed


def main():
    ok = asyncio.run(test_sub_server_deployment())
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
