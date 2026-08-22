#!/usr/bin/env python3
"""
Test: Freedom Node Deployment (deploy_mode: freedom_only)
Spins up vps-freedom container and deploys Freedom Node into it.
Verifies Caddy TLS, 3x-UI panel inbounds, and subscription URL generation.
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
    fetch_panel_html,
    log,
)

SSH_PORT = 2221
DOMAIN = "freedom-only.test"
CONTAINER_NAME = "vps-freedom-only"


async def test_freedom_deployment() -> bool:
    ensure_test_containers_running(CONTAINER_NAME)

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

    log("Starting Freedom Node deployment via ssh_deployer...", "info")
    ok, result = await run_deployment(config, log)

    if not ok:
        log("Freedom Node deployment failed!", "error")
        return False

    log("Freedom Node deployment returned success!", "success")
    log(f"Result details: {result}", "info")

    # 1. Verify expected containers are running inside vps-freedom-only
    if not check_inner_containers_running(CONTAINER_NAME, ["3xui", "caddy", "nginx-decoy"]):
        return False

    # 2. Verify HTTPS response via Caddy on domain
    sub_secret = config["sub_secret"]
    web_base_path = hashlib.md5(f"{sub_secret}-panel".encode("utf-8")).hexdigest()[:16]
    sub_base_path = hashlib.md5(f"{sub_secret}-sub".encode("utf-8")).hexdigest()[:16]

    panel_html = fetch_panel_html(CONTAINER_NAME, f"https://{DOMAIN}/{web_base_path}/")
    if "3X-UI" not in panel_html and "login" not in panel_html.lower() and "html" not in panel_html.lower():
        log(f"3x-UI web panel did not return expected HTML! Output:\n{panel_html[:500]}", "error")
        return False
    log("3x-UI web panel is accessible!", "success")

    # 3. Verify subscription via real TLS (host --resolve through Caddy)
    log("Verifying subscription via host TLS (--resolve through Caddy)...", "info")
    tls_sub_path = f"{sub_base_path}/local-proxy-node-client"
    tls_status, tls_body = fetch_subscription_via_host_tls(CONTAINER_NAME, DOMAIN, tls_sub_path)
    if tls_status != 200:
        log(f"TLS subscription check failed: HTTP {tls_status} (expected 200)", "error")
        return False
    tls_links = decode_vless_subscription(tls_body)
    if not tls_links:
        log("TLS subscription returned valid HTTP 200 but failed to decode base64!", "error")
        return False
    log(f"TLS subscription OK ({len(tls_links)} vless link(s) via Caddy L4)", "success")

    log("=========================================", "success")
    log("🎉 TEST FREEDOM NODE DEPLOYMENT PASSED! 🎉", "success")
    log("=========================================", "success")
    return True


def main():
    ok = asyncio.run(test_freedom_deployment())
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
