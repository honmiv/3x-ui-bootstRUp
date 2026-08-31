#!/usr/bin/env python3
"""
Test: Subscription Server Deployment (deploy_mode: sub_only)
Spins up vps-sub-only container and deploys Sub-Server into it.
Verifies Caddy TLS, subs-server container, admin dashboard login, and client endpoints.
"""

import asyncio
import base64
import json
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
    check_inner_containers_running,
    decode_vless_subscription,
    ensure_test_containers_running,
    fetch_subscription_via_host_tls,
    log,
    TLS_HOST_PORTS,
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

    log(f"Starting Subscription Server deployment on {CONTAINER_NAME} via ssh_deployer...", "info")
    ok, result = await run_deployment(config, log)

    if not ok:
        log("Subscription Server deployment failed!", "error")
        return False

    log("Subscription Server deployment returned success!", "success")
    log(f"Result details: {result}", "info")

    derived_sub_path = hashlib.md5(SECRET_SUB_PATH.encode("utf-8")).hexdigest()[:16]

    # 1. Verify expected containers are running inside vps-sub-only
    if not check_inner_containers_running(CONTAINER_NAME, ["subs-server", "sub-caddy", "sub-nginx-decoy"]):
        return False

    # 2. Verify HTTPS response via Caddy on login
    res = subprocess.run(
        [
            "docker",
            "exec",
            CONTAINER_NAME,
            "curl",
            "-s",
            "-k",
            "-L",
            f"https://{DOMAIN}/{derived_sub_path}/login",
        ],
        capture_output=True,
        text=True,
    )
    if "3x-UI Subs" not in res.stdout and "login" not in res.stdout.lower() and "пароль" not in res.stdout.lower():
        log(f"Sub-Server admin login page did not return expected HTML! Output:\n{res.stdout[:500]}", "error")
        return False
    else:
        log("Sub-Server admin login is accessible through Caddy TLS proxy!", "success")

    # 3. Test invalid client returns 404/Empty
    res_404 = subprocess.run(
        [
            "docker",
            "exec",
            CONTAINER_NAME,
            "curl",
            "-s",
            "-k",
            "-w",
            "%{http_code}",
            f"https://{DOMAIN}/{derived_sub_path}/nonexistent-client",
        ],
        capture_output=True,
        text=True,
    )
    if res_404.stdout.endswith("404") or "404" in res_404.stdout:
        log("Sub-Server correctly returns 404 for unknown client!", "success")
    else:
        log(f"Sub-Server response for unknown client: {res_404.stdout}", "info")

    # ------------------------------------------------------------------
    # 4. Force-subs override test
    #    force-subs.yml is excluded from the deployment bundle by design
    #    (production preserves user overrides). Inject the test override
    #    into the running container and restart subs-server.
    # ------------------------------------------------------------------
    FAKE_CLIENT = "user1-tcp"
    FAKE_VLESS = (
        "vless://00000000-0000-0000-0000-000000000001@fake-host.test:443"
        "?encryption=none&flow=xtls-rprx-vision&security=reality"
        "&sni=fake-host.test&fp=chrome&pbk=FakePublicKey1234567890123456789012"
        "&sid=abcd1234&type=tcp&name=fake-override#force-test"
    )
    FAKE_FORCE_SUBS = f"# force-subs.yml\n{FAKE_CLIENT}: {base64.b64encode(FAKE_VLESS.encode()).decode()}\n"
    REMOTE_FORCE_PATH = "/opt/3x-ui-bootstRUp/sub-server/force-subs.yml"

    log("Injecting test force-subs.yml override into container...", "info")
    # Write via docker exec (file is bind-mounted into subs-server at /data/force-subs.yml)
    write_cmd = f"cat > {REMOTE_FORCE_PATH} <<'TESTEOF'\n{FAKE_FORCE_SUBS}TESTEOF"
    wr = subprocess.run(
        ["docker", "exec", CONTAINER_NAME, "sh", "-c", write_cmd],
        capture_output=True, text=True,
    )
    if wr.returncode != 0:
        log(f"Failed to write force-subs.yml: {wr.stderr}", "error")
        return False
    # Verify
    cat_res = subprocess.run(
        ["docker", "exec", CONTAINER_NAME, "cat", REMOTE_FORCE_PATH],
        capture_output=True, text=True,
    )
    if FAKE_CLIENT not in cat_res.stdout:
        log(f"force-subs.yml verification failed: {cat_res.stdout[:200]}", "error")
        return False
    log("force-subs.yml injected!", "success")

    log("Restarting subs-server container...", "info")
    restart_res = subprocess.run(
        ["docker", "exec", CONTAINER_NAME, "docker", "restart", "subs-server"],
        capture_output=True, text=True,
    )
    if restart_res.returncode != 0:
        log(f"Failed to restart subs-server: {restart_res.stderr}", "error")
        return False
    time.sleep(3)
    log("subs-server restarted!", "success")

    # Verify containers still running after restart
    if not check_inner_containers_running(CONTAINER_NAME, ["subs-server", "sub-caddy", "sub-nginx-decoy"]):
        return False

    # 5a. Fetch user1-tcp → 200 with pre-seeded fake vless content
    log(f"Fetching subscription for '{FAKE_CLIENT}' (expect 200 with pre-seeded override)...", "info")
    ov_status, ov_body = fetch_subscription_via_host_tls(CONTAINER_NAME, DOMAIN, f"{derived_sub_path}/{FAKE_CLIENT}")
    if ov_status != 200:
        log(f"Pre-seeded override fetch failed: status={ov_status}", "error")
        return False
    # Body is base64-encoded vless:// URL (force-subs stores values as base64)
    ov_links = decode_vless_subscription(ov_body)
    if not ov_links:
        log(f"Pre-seeded override returned 200 but decode failed. Body: {ov_body[:200]}", "error")
        return False
    if "fake-host.test" not in ov_links[0]:
        log(f"Override decoded but wrong content: {ov_links[0][:100]}", "error")
        return False
    log(f"Pre-seeded override OK: {len(ov_links)} link(s), matches fake-host.test", "success")

    # 5b. Login and clear the override — all through Caddy TLS (host-side)
    ADMIN_USER = config["sub_admin_user"]
    ADMIN_PASS = config["sub_admin_password"]
    tls_port = TLS_HOST_PORTS[CONTAINER_NAME]
    base_url = f"https://{DOMAIN}:{tls_port}/{derived_sub_path}"

    log("Logging in to clear override...", "info")
    login_res = subprocess.run(
        [
            "curl", "-sk", "-D", "-", "-o", "/dev/null",
            "--resolve", f"{DOMAIN}:{tls_port}:127.0.0.1",
            "-X", "POST", f"{base_url}/login",
            "-d", f"user={ADMIN_USER}&password={ADMIN_PASS}",
            "-H", "Content-Type: application/x-www-form-urlencoded",
        ],
        capture_output=True, text=True, timeout=15,
    )
    cookie_str = ""
    for line in login_res.stdout.splitlines():
        if "set-cookie" in line.lower() and "sub_session" in line:
            cookie_str = line.split(":", 1)[1].strip().split(";")[0].strip()
            break
    if not cookie_str:
        log(f"Failed to obtain session cookie. Headers:\n{login_res.stdout}", "error")
        return False
    log("Login successful!", "success")

    log(f"Clearing override for '{FAKE_CLIENT}'...", "info")
    clear_body = json.dumps({"client": FAKE_CLIENT, "value": ""})
    cl_res = subprocess.run(
        [
            "curl", "-sk", "-w", "\n%{http_code}",
            "--resolve", f"{DOMAIN}:{tls_port}:127.0.0.1",
            "-X", "POST", f"{base_url}/api/override",
            "-d", clear_body,
            "-H", "Content-Type: application/json",
            "-b", cookie_str,
        ],
        capture_output=True, text=True, timeout=15,
    )
    cl_lines = cl_res.stdout.rsplit("\n", 1)
    cl_status = int(cl_lines[-1].strip()) if cl_lines[-1].strip().isdigit() else 0
    cl_resp = cl_lines[0] if len(cl_lines) > 1 else cl_res.stdout
    if cl_status != 200 or '"ok"' not in cl_resp:
        log(f"Clear override failed: status={cl_status}, body={cl_resp}", "error")
        return False
    log("Override cleared!", "success")

    # 5c. Fetch again → 502 (backend unreachable, override gone)
    log(f"Fetching '{FAKE_CLIENT}' after clear (expect 502)...", "info")
    cl_status2, _ = fetch_subscription_via_host_tls(CONTAINER_NAME, DOMAIN, f"{derived_sub_path}/{FAKE_CLIENT}")
    if cl_status2 == 502:
        log("After clearing override: 502 — correct!", "success")
    else:
        log(f"Expected 502 after clearing, got {cl_status2}", "error")
        return False

    # 6. Test update_sub mode preserves clients in nodes.json
    log("Testing 'update_sub' deployment mode...", "info")
    update_config = {
        "deploy_mode": "update_sub",
        "sub_vps_host": "127.0.0.1",
        "sub_vps_port": SSH_PORT,
        "sub_vps_user": "root",
        "sub_vps_password": "root",
        "bundle_source_dir": prepare_test_repo("panel", "sub-server"),
    }
    up_ok, up_result = await run_deployment(update_config, log)
    if not up_ok:
        log("update_sub deployment failed!", "error")
        return False

    # Verify nodes.json still has clients
    nodes_check = subprocess.run(
        ["docker", "exec", CONTAINER_NAME, "cat", "/opt/3x-ui-bootstRUp/sub-server/nodes.json"],
        capture_output=True, text=True,
    )
    if "user1-tcp" not in nodes_check.stdout or "freedom-direct" not in nodes_check.stdout:
        log(f"update_sub failed to preserve clients! nodes.json content:\n{nodes_check.stdout}", "error")
        return False
    log("update_sub preserved all clients in nodes.json!", "success")

    log("===============================================", "success")
    log("🎉 TEST SUBSCRIPTION SERVER DEPLOYMENT PASSED! 🎉", "success")
    log("===============================================", "success")
    return True


def main():
    ok = asyncio.run(test_sub_server_deployment())
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
