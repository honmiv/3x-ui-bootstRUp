#!/usr/bin/env python3
"""
Test: Subscription Server Deployment + Subscription Fetch
Deploys Sub-Server and fetches subscriptions via host TLS through Caddy.
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

SSH_PORT = 2223
DOMAIN = "sub-only.test"
CONTAINER_NAME = "vps-sub-only"
SECRET_SUB_PATH = "subs"


async def test_sub_server_deployment() -> bool:
    ensure_test_containers_running(CONTAINER_NAME)

    config = {
        "deploy_mode": "sub_only",
        "sub_vps_host": "127.0.0.1",
        "sub_vps_port": SSH_PORT,
        "sub_vps_user": "root",
        "sub_vps_password": "root",
        "sub_domain": DOMAIN,
        "sub_secret_path": SECRET_SUB_PATH,
        "sub_russian_url": "https://proxy-only.test/proxy-sub",
        "sub_foreign_url": "https://sub-foreign.test/freedom-sub",
        "sub_proxy_clients": "user1-tcp, user2-xhttp",
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

    for client in ["user1-tcp", "user2-xhttp", "freedom-direct"]:
        path = f"{SECRET_SUB_PATH}/{client}"
        log(f"Fetching subscription for '{client}'...", "info")
        status, body = fetch_subscription_via_host_tls(CONTAINER_NAME, DOMAIN, path)
        links = decode_vless_subscription(body)
        log(f"{client}: status={status}, links={len(links) if links else 0}", "info")
        if links:
            log(f"{client} vless: {links[0][:80]}...", "info")

    return True


def main():
    ok = asyncio.run(test_sub_server_deployment())
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
