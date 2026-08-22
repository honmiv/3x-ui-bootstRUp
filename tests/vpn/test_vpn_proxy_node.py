#!/usr/bin/env python3
"""
Test: Proxy Node Deployment + Subscription Fetch
Deploys Proxy Node (with foreign backend) and fetches subscriptions via host TLS.
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

SSH_PORT = 2222
DOMAIN = "proxy-only.test"
CONTAINER_NAME = "vps-proxy-only"

FOREIGN_SSH_PORT = 2225
FOREIGN_DOMAIN = "proxy-foreign.test"
FOREIGN_CONTAINER = "vps-proxy-foreign"


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

    for label, path in [("TCP", "proxy-user-tcp"), ("XHTTP", "proxy-user-xhttp")]:
        sub_path = f"{sub_base_path}/{path}"
        log(f"Fetching {label} subscription: {sub_path}...", "info")
        status, body = fetch_subscription_via_host_tls(CONTAINER_NAME, DOMAIN, sub_path)
        links = decode_vless_subscription(body)
        log(f"{label} subscription: status={status}, links={len(links) if links else 0}", "info")
        if links:
            log(f"{label} vless: {links[0][:80]}...", "info")

    return True


def main():
    ok = asyncio.run(test_proxy_deployment())
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
