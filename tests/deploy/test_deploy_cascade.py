#!/usr/bin/env python3
"""
Test: Two-Node Cascade Deployment (deploy_mode: cascade)
Spins up vps-cascade-freedom and vps-cascade-proxy containers.
Executes automated 2-stage deployment: Freedom Node -> Proxy Node with outbound subscription.
Verifies both nodes, TLS, and generated cascade client subscriptions.
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

FREEDOM_PORT = 2231
FREEDOM_DOMAIN = "cascade-freedom.test"
FREEDOM_CONTAINER = "vps-cascade-freedom"

PROXY_PORT = 2232
PROXY_DOMAIN = "cascade-proxy.test"
PROXY_CONTAINER = "vps-cascade-proxy"


async def test_cascade_deployment() -> bool:
    ensure_test_containers_running(FREEDOM_CONTAINER, PROXY_CONTAINER)

    config = {
        "deploy_mode": "cascade",
        "is_cascade": True,
        "freedom_host": FREEDOM_DOMAIN,
        "freedom_host_for_ssh": "127.0.0.1",
        "freedom_port": FREEDOM_PORT,
        "freedom_user": "root",
        "freedom_password": "root",
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
        "proxy_xui_username": "proxyadmin",
        "proxy_xui_password": "ProxyAdminPassword123!",
        "proxy_sub_secret": "proxy_cascade_secret_key",
        "proxy_client_tcp_list": "cascade-user-tcp",
        "proxy_client_xhttp_list": "cascade-user-xhttp",
        "proxy_xui_version": "3.6.0",

        "bundle_source_dir": prepare_test_repo("panel"),
    }

    log("Starting 2-Stage Cascade Deployment via ssh_deployer...", "info")
    ok, result = await run_deployment(config, log)

    if not ok:
        log("Cascade deployment failed!", "error")
        return False

    log("Cascade deployment returned success!", "success")
    log(f"Result details: {result}", "info")

    # 1. Verify Freedom Node containers
    if not check_inner_containers_running(FREEDOM_CONTAINER, ["3xui", "caddy", "nginx-decoy"]):
        return False

    # 2. Verify Proxy Node containers
    if not check_inner_containers_running(PROXY_CONTAINER, ["3xui", "caddy", "nginx-decoy"]):
        return False

    # 3. Verify Freedom Node TLS
    f_secret = config["freedom_sub_secret"]
    f_web_base = hashlib.md5(f"{f_secret}-panel".encode("utf-8")).hexdigest()[:16]
    panel_f = fetch_panel_html(FREEDOM_CONTAINER, f"https://{FREEDOM_DOMAIN}/{f_web_base}/")
    if "3X-UI" not in panel_f and "login" not in panel_f.lower() and "html" not in panel_f.lower():
        log("Freedom Node 3x-UI web panel check failed!", "error")
        return False
    log("Freedom Node web panel is operational.", "success")

    # 4. Verify Proxy Node TLS
    p_secret = config["proxy_sub_secret"]
    p_web_base = hashlib.md5(f"{p_secret}-panel".encode("utf-8")).hexdigest()[:16]
    panel_p = fetch_panel_html(PROXY_CONTAINER, f"https://{PROXY_DOMAIN}/{p_web_base}/")
    if "3X-UI" not in panel_p and "login" not in panel_p.lower() and "html" not in panel_p.lower():
        log("Proxy Node 3x-UI web panel check failed!", "error")
        return False
    log("Proxy Node web panel is operational.", "success")

    # 5. Verify TLS on both nodes via host --resolve (Caddy L4 end-to-end)
    p_sub_base = hashlib.md5(f"{p_secret}-sub".encode("utf-8")).hexdigest()[:16]
    f_sub_base = hashlib.md5(f"{config['freedom_sub_secret']}-sub".encode("utf-8")).hexdigest()[:16]
    tls_checks = [
        ("Freedom node", FREEDOM_CONTAINER, FREEDOM_DOMAIN, f"{f_sub_base}/local-proxy-node-client"),
        ("Proxy node", PROXY_CONTAINER, PROXY_DOMAIN, f"{p_sub_base}/cascade-user-tcp"),
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
    log("=========================================", "success")
    log("🎉 TEST CASCADE DEPLOYMENT PASSED! 🎉", "success")
    log("=========================================", "success")
    return True


def main():
    ok = asyncio.run(test_cascade_deployment())
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
