#!/usr/bin/env python3
"""
Test: 3-Stage Cascade + Subscription Server Deployment + Subscription Fetch
Deploys Freedom, Proxy, and Sub-Server nodes, then fetches subscriptions via host TLS.
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
    decode_vless_subscription,
    ensure_test_containers_running,
    fetch_subscription_via_host_tls,
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


async def test_cascade_sub_deployment() -> bool:
    ensure_test_containers_running(FREEDOM_CONTAINER, PROXY_CONTAINER, SUB_CONTAINER)

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

    for label, container, domain, path in checks:
        log(f"Fetching {label} subscription: {path}...", "info")
        status, body = fetch_subscription_via_host_tls(container, domain, path)
        links = decode_vless_subscription(body)
        log(f"{label}: status={status}, links={len(links) if links else 0}", "info")
        if links:
            log(f"{label} vless: {links[0][:80]}...", "info")

    return True


def main():
    ok = asyncio.run(test_cascade_sub_deployment())
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
