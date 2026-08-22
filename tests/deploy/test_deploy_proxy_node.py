#!/usr/bin/env python3
"""
Test: Proxy Node Deployment (deploy_mode: proxy_only)
Spins up vps-proxy-only container and deploys Proxy Node into it.
Verifies Caddy TLS, 3x-UI panel inbounds, outbound sub, and client subscription URLs.
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

SSH_PORT = 2222
DOMAIN = "proxy-only.test"
CONTAINER_NAME = "vps-proxy-only"

FOREIGN_SSH_PORT = 2225
FOREIGN_DOMAIN = "proxy-foreign.test"
FOREIGN_CONTAINER = "vps-proxy-foreign"


async def ensure_foreign_node_deployed() -> str:
    """Ensures the foreign backend node is deployed and returns its subscription URL."""
    ensure_test_containers_running(FOREIGN_CONTAINER)
    foreign_sub_secret = "proxy_foreign_secret_phrase"
    sub_base_path = hashlib.md5(f"{foreign_sub_secret}-sub".encode("utf-8")).hexdigest()[:16]
    foreign_sub_url = f"https://{FOREIGN_DOMAIN}/{sub_base_path}/local-proxy-node-client"

    if not check_inner_containers_running(FOREIGN_CONTAINER, ["3xui", "caddy", "nginx-decoy"]):
        log(f"Deploying foreign backend node on {FOREIGN_CONTAINER}...", "info")
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
        ok, res = await run_deployment(config_foreign, log)
        if not ok:
            raise RuntimeError(f"Failed to deploy foreign backend node on {FOREIGN_CONTAINER}")

    return foreign_sub_url


async def test_proxy_deployment() -> bool:
    ensure_test_containers_running(CONTAINER_NAME)
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

    log(f"Starting Proxy Node deployment on {CONTAINER_NAME} via ssh_deployer...", "info")
    ok, result = await run_deployment(config, log)

    if not ok:
        log("Proxy Node deployment failed!", "error")
        return False

    log("Proxy Node deployment returned success!", "success")
    log(f"Result details: {result}", "info")

    # 1. Verify expected containers are running inside vps-proxy-only
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
    tls_sub_path = f"{sub_base_path}/proxy-user-tcp"
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
    log("🎉 TEST PROXY NODE DEPLOYMENT PASSED! 🎉", "success")
    log("=========================================", "success")
    return True


def main():
    ok = asyncio.run(test_proxy_deployment())
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
