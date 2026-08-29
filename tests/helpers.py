#!/usr/bin/env python3
"""
Common testing helpers for 3x-ui-bootstRUp integration tests.
"""

import base64
import fcntl
import os
import socket
import subprocess
import sys
import time
from urllib.parse import urlsplit
from typing import List

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

COMPOSE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "docker-compose.test.yml")

SERVICE_PORTS = {
    "vps-freedom-only": 2221,
    "vps-proxy-only": 2222,
    "vps-sub-only": 2223,
    "vps-proxy-foreign": 2225,
    "vps-sub-foreign": 2226,
    "vps-cascade-freedom": 2231,
    "vps-cascade-proxy": 2232,
    "vps-cascadesub-freedom": 2241,
    "vps-cascadesub-proxy": 2242,
    "vps-cascadesub-sub": 2243,
    "vps-freedomsub-freedom": 2251,
    "vps-freedomsub-sub": 2252,
}

# Host-side TLS ports (container :443 → host :PORT) for --resolve testing
TLS_HOST_PORTS = {
    "vps-freedom-only": 8441,
    "vps-proxy-only": 8442,
    "vps-sub-only": 8555,
    "vps-cascade-freedom": 8451,
    "vps-cascade-proxy": 8452,
    "vps-cascadesub-freedom": 8461,
    "vps-cascadesub-proxy": 8462,
    "vps-cascadesub-sub": 8463,
    "vps-freedomsub-freedom": 8471,
    "vps-freedomsub-sub": 8472,
}


def get_outer_docker_ip(container_name: str) -> str:
    """Get the outer Docker network IP of a test VPS container."""
    result = subprocess.run(
        ["docker", "inspect", container_name, "--format", "{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}"],
        capture_output=True, text=True,
    )
    ip = result.stdout.strip()
    if not ip:
        raise RuntimeError(f"Cannot determine outer IP for container {container_name}")
    return ip


def log(msg: str, level: str = "info"):
    colors = {
        "info": "\033[0;36m",
        "success": "\033[0;32m",
        "warn": "\033[0;33m",
        "error": "\033[0;31m",
        "reset": "\033[0m",
    }
    c = colors.get(level, colors["info"])
    r = colors["reset"]
    print(f"{c}[{level.upper()}]{r} {msg}", flush=True)


def ensure_caddy_l4_cached():
    """
    Ensures required images (caddy-l4, 3x-ui, nginx, python) are saved to tests/.cache/*.tar.
    This archive is mounted into the test VPS containers so dockerd can pre-load them instantly.
    """
    cache_dir = os.path.join(REPO_ROOT, "tests", ".cache")
    os.makedirs(cache_dir, exist_ok=True)

    # 1. caddy-l4
    caddy_tar = os.path.join(cache_dir, "caddy-l4.tar")
    if not (os.path.exists(caddy_tar) and os.path.getsize(caddy_tar) > 1024):
        log("Building caddy-l4 once on host Docker for local test cache...", "info")
        dockerfile = os.path.join(REPO_ROOT, "panel", "templates", "docker-compose", "Dockerfile-caddy-l4")
        context_dir = os.path.join(REPO_ROOT, "panel", "templates", "docker-compose")
        res = subprocess.run(
            ["docker", "build", "-t", "ghcr.io/honmiv/caddy-l4:latest", "-f", dockerfile, context_dir],
            capture_output=True,
            text=True,
        )
        if res.returncode == 0:
            subprocess.run(["docker", "save", "ghcr.io/honmiv/caddy-l4:latest", "-o", caddy_tar], capture_output=True)

    # 2. 3x-ui
    xui_tar = os.path.join(cache_dir, "3xui.tar")
    if not (os.path.exists(xui_tar) and os.path.getsize(xui_tar) > 1024):
        log("Pulling and caching 3x-ui 3.6.0...", "info")
        subprocess.run(["docker", "pull", "ghcr.io/mhsanaei/3x-ui:3.6.0"], capture_output=True)
        subprocess.run(["docker", "save", "ghcr.io/mhsanaei/3x-ui:3.6.0", "-o", xui_tar], capture_output=True)

    # 3. nginx-decoy
    nginx_tar = os.path.join(cache_dir, "nginx.tar")
    if not (os.path.exists(nginx_tar) and os.path.getsize(nginx_tar) > 1024):
        log("Pulling and caching nginx:1.27-alpine...", "info")
        subprocess.run(["docker", "pull", "nginx:1.27-alpine"], capture_output=True)
        subprocess.run(["docker", "save", "nginx:1.27-alpine", "-o", nginx_tar], capture_output=True)

    # 4. python alpine
    py_tar = os.path.join(cache_dir, "python.tar")
    if not (os.path.exists(py_tar) and os.path.getsize(py_tar) > 1024):
        log("Pulling and caching python:3.12-alpine...", "info")
        subprocess.run(["docker", "pull", "python:3.12-alpine"], capture_output=True)
        subprocess.run(["docker", "save", "python:3.12-alpine", "-o", py_tar], capture_output=True)

    # 5. xray-core
    xray_tar = os.path.join(cache_dir, "xray.tar")
    if not (os.path.exists(xray_tar) and os.path.getsize(xray_tar) > 1024):
        log("Pulling and caching ghcr.io/xtls/xray-core:latest...", "info")
        subprocess.run(["docker", "pull", "ghcr.io/xtls/xray-core:latest"], capture_output=True)
        subprocess.run(["docker", "save", "ghcr.io/xtls/xray-core:latest", "-o", xray_tar], capture_output=True)

    # 6. caddy:2 (sub-server)
    caddy2_tar = os.path.join(cache_dir, "caddy2.tar")
    if not (os.path.exists(caddy2_tar) and os.path.getsize(caddy2_tar) > 1024):
        log("Pulling and caching caddy:2...", "info")
        subprocess.run(["docker", "pull", "caddy:2"], capture_output=True)
        subprocess.run(["docker", "save", "caddy:2", "-o", caddy2_tar], capture_output=True)


def ensure_test_containers_running(*service_names: str):
    """
    Spins up only the requested test container services (e.g. 'vps-freedom', 'vps-proxy')
    and waits for their SSH server and inner Docker daemon to be fully ready.
    """
    ensure_caddy_l4_cached()

    if not service_names:
        service_names = ("vps-freedom",)

    log(f"Ensuring test containers are running: {', '.join(service_names)}...", "info")
    cmd = ["docker", "compose", "-f", COMPOSE_FILE, "up", "-d", "--build"] + list(service_names)
    lock_file_path = "/tmp/3xui_test_compose_up.lock"
    with open(lock_file_path, "w") as lock_file:
        fcntl.flock(lock_file, fcntl.LOCK_EX)
        try:
            res = subprocess.run(
                cmd,
                cwd=os.path.dirname(COMPOSE_FILE),
                capture_output=True,
                text=True,
            )
        finally:
            fcntl.flock(lock_file, fcntl.LOCK_UN)
    if res.returncode != 0:
        log(f"Failed to start test containers: {res.stderr}", "error")
        sys.exit(1)

    for srv in service_names:
        port = SERVICE_PORTS.get(srv)
        if not port:
            continue

        log(f"Waiting for SSH on 127.0.0.1:{port} ({srv})...", "info")
        for _ in range(45):
            try:
                with socket.create_connection(("127.0.0.1", port), timeout=2):
                    break
            except (socket.timeout, ConnectionRefusedError, OSError):
                time.sleep(1)
        else:
            log(f"Timed out waiting for SSH on port {port} ({srv})", "error")
            sys.exit(1)

        log(f"Waiting for inner Docker daemon in {srv}...", "info")
        for _ in range(45):
            res = subprocess.run(
                ["docker", "exec", srv, "docker", "info"],
                capture_output=True,
                text=True,
            )
            if res.returncode == 0:
                log(f"Inner Docker daemon in {srv} is ready!", "success")
                break
            time.sleep(1)
        else:
            log(f"Timed out waiting for inner Docker daemon in {srv}", "error")
            sys.exit(1)


def check_inner_containers_running(vps_name: str, expected_containers: List[str]) -> bool:
    """Verifies that the expected Docker services are running inside the simulated VPS."""
    res = subprocess.run(
        ["docker", "exec", vps_name, "docker", "ps", "--format", "{{.Names}}"],
        capture_output=True,
        text=True,
    )
    running = res.stdout.split()
    log(f"Containers running inside {vps_name}: {running}", "info")
    for exp in expected_containers:
        if exp not in running:
            log(f"Expected container '{exp}' NOT found in {vps_name}!", "error")
            return False
    log(f"All expected containers {expected_containers} are running in {vps_name}!", "success")
    return True



def fetch_subscription_via_host_tls(container_name: str, domain: str, sub_path: str) -> tuple:
    """Fetch subscription via host-side curl --resolve to test real TLS through Caddy.

    Returns (status_code, body) tuple. Status 200 = valid subscription,
    404 = unknown client, 502 = backend unreachable, 0 = connection failed.
    """
    tls_port = TLS_HOST_PORTS.get(container_name)
    if tls_port is None:
        log(f"No TLS host port mapping for {container_name}", "warn")
        return 0, ""
    url = f"https://{domain}:{tls_port}/{sub_path}"
    log(f"Fetching subscription from {url} via host-side curl --resolve...", "info")
    res = subprocess.run(
        [
            "curl", "-sk", "-o", "/dev/null", "-w", "%{http_code}",
            "--resolve", f"{domain}:{tls_port}:127.0.0.1",
            url,
        ],
        capture_output=True,
        text=True,
        timeout=15,
    )
    status = int(res.stdout.strip()) if res.stdout.strip().isdigit() else 0
    # Fetch body separately for decoding
    res_body = subprocess.run(
        [
            "curl", "-sk",
            "--resolve", f"{domain}:{tls_port}:127.0.0.1",
            url,
        ],
        capture_output=True,
        text=True,
        timeout=15,
    )
    return status, res_body.stdout.strip()


def fetch_panel_html(vps_name: str, panel_url: str) -> str:
    """Fetch panel HTML, falling back to 3x-ui's internal web port."""
    res = subprocess.run(
        ["docker", "exec", vps_name, "curl", "-s", "-k", "-L", panel_url],
        capture_output=True, text=True,
    )
    if res.stdout.strip():
        return res.stdout
    parsed = urlsplit(panel_url)
    caddyfile = "/opt/3x-ui-bootstRUp/working/caddy/Caddyfile"
    internal_cmd = (
        "port=$(sed -n 's/.*reverse_proxy @web_base_path 3xui:\\([0-9]*\\).*/\\1/p' "
        f"{caddyfile} | head -n 1); "
        "[ -n \"$port\" ] && docker exec 3xui curl -sL "
        f"http://127.0.0.1:$port{parsed.path} || true"
    )
    fallback = subprocess.run(
        ["docker", "exec", vps_name, "sh", "-c", internal_cmd],
        capture_output=True, text=True,
    )
    return fallback.stdout


def decode_vless_subscription(raw_b64: str) -> List[str]:
    """Decodes base64 subscription and returns non-empty lines."""
    try:
        decoded = base64.b64decode(raw_b64).decode("utf-8", errors="replace")
        lines = [line.strip() for line in decoded.splitlines() if line.strip()]
        lines = [line for line in lines if line.startswith("vless://")]
        return lines
    except Exception as e:
        log(f"Failed to decode base64 subscription: {e}", "error")
        return []


def get_container_ip(container_name: str, network_name: str = "testnet") -> str:
    """Returns the IP address of a container inside the given network."""
    cmd = [
        "docker",
        "inspect",
        "-f",
        f"{{{{.NetworkSettings.Networks.{network_name}.IPAddress}}}}",
        container_name,
    ]
    res = subprocess.run(cmd, capture_output=True, text=True)
    ip = res.stdout.strip()
    if not ip:
        # Fallback if network name format differs
        cmd_fallback = [
            "docker",
            "inspect",
            "-f",
            "{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}",
            container_name,
        ]
        res_fb = subprocess.run(cmd_fallback, capture_output=True, text=True)
        ip = res_fb.stdout.strip()
    return ip


def parse_vless_url(vless_str: str) -> dict:
    """Parses a vless:// URL into structured parameters dictionary."""
    import urllib.parse

    vless_str = vless_str.strip()
    if not vless_str.startswith("vless://"):
        raise ValueError(f"Invalid VLESS URL: {vless_str[:30]}...")

    parsed = urllib.parse.urlparse(vless_str)
    uuid = parsed.username or ""
    server_address = parsed.hostname or ""
    port = parsed.port or 443

    params = urllib.parse.parse_qs(parsed.query)

    return {
        "uuid": uuid,
        "address": server_address,
        "port": port,
        "encryption": params.get("encryption", ["none"])[0],
        "flow": params.get("flow", [""])[0],
        "security": params.get("security", ["reality"])[0],
        "pbk": params.get("pbk", [""])[0],
        "sid": params.get("sid", [""])[0],
        "sni": params.get("sni", [server_address])[0],
        "spx": urllib.parse.unquote(params.get("spx", ["/"])[0]),
        "type": params.get("type", ["tcp"])[0],
        "path": urllib.parse.unquote(params.get("path", ["/"])[0]),
        "mode": params.get("mode", ["auto"])[0],
        "name": parsed.fragment or "",
        "raw_url": vless_str,
    }


def generate_xray_client_config(
    vless_data: dict, socks_port: int = 10808, http_port: int = 10809
) -> dict:
    """Generates an XRay client config dictionary from parsed VLESS parameters."""
    outbound_stream_settings = {
        "network": vless_data["type"],
        "security": vless_data["security"],
        "realitySettings": {
            "show": False,
            "fingerprint": "firefox",
            "serverName": vless_data["sni"],
            "publicKey": vless_data["pbk"],
            "shortId": vless_data["sid"],
            "spiderX": vless_data["spx"],
        },
    }

    if vless_data["type"] == "xhttp":
        outbound_stream_settings["xhttpSettings"] = {
            "mode": vless_data.get("mode", "auto"),
            "path": vless_data.get("path", "/"),
            "host": vless_data.get("sni", vless_data["address"]),
        }

    user_entry = {
        "id": vless_data["uuid"],
        "encryption": vless_data.get("encryption", "none"),
    }
    if vless_data.get("flow"):
        user_entry["flow"] = vless_data["flow"]

    return {
        "log": {"loglevel": "warning"},
        "inbounds": [
            {
                "tag": "socks-in",
                "port": socks_port,
                "listen": "0.0.0.0",
                "protocol": "socks",
                "settings": {"auth": "noauth", "udp": True},
            },
            {
                "tag": "http-in",
                "port": http_port,
                "listen": "0.0.0.0",
                "protocol": "http",
                "settings": {},
            },
        ],
        "outbounds": [
            {
                "tag": "proxy",
                "protocol": "vless",
                "settings": {
                    "vnext": [
                        {
                            "address": vless_data["address"],
                            "port": vless_data["port"],
                            "users": [user_entry],
                        }
                    ]
                },
                "streamSettings": outbound_stream_settings,
            }
        ],
    }


def start_xray_test_client(
    client_config_dict: dict, container_name: str = "vps-test-client"
) -> bool:
    """Runs an ephemeral XRay Core client container in the testnet network."""
    import json

    stop_xray_test_client(container_name)

    cache_dir = os.path.join(REPO_ROOT, "tests", ".cache")
    os.makedirs(cache_dir, exist_ok=True)
    config_file = os.path.join(cache_dir, f"xray_{container_name}.json")

    config_json = json.dumps(client_config_dict, indent=2)
    with open(config_file, "w", encoding="utf-8") as f:
        f.write(config_json)

    cmd = [
        "docker",
        "run",
        "-d",
        "--name",
        container_name,
        "--network",
        "testnet",
        "-v",
        f"{config_file}:/etc/xray/config.json:ro",
        "ghcr.io/xtls/xray-core:latest",
        "run",
        "-c",
        "/etc/xray/config.json",
    ]

    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0:
        log(f"Failed to start {container_name}: {res.stderr}", "error")
        return False

    # Wait for container to be in running state
    time.sleep(2)
    check = subprocess.run(
        ["docker", "inspect", "-f", "{{.State.Running}}", container_name],
        capture_output=True,
        text=True,
    )
    if check.stdout.strip() != "true":
        logs = subprocess.run(
            ["docker", "logs", container_name], capture_output=True, text=True
        )
        log(f"XRay test client container crashed! Logs:\n{logs.stderr}\n{logs.stdout}", "error")
        return False

    log(f"XRay test client '{container_name}' started successfully!", "success")
    return True


def stop_xray_test_client(container_name: str = "vps-test-client"):
    """Stops and removes the ephemeral XRay client container."""
    subprocess.run(
        ["docker", "rm", "-f", container_name],
        capture_output=True,
        text=True,
    )


def query_echo_server_via_vpn(
    runner_container: str = "vps-freedom",
    proxy_client_name: str = "vps-test-client",
    socks_port: int = 10808,
    target_url: str = "http://echo.test/ip",
) -> dict:
    """
    Executes a curl request through the SOCKS5 proxy of vps-test-client
    from inside one of the testnet containers (e.g. vps-freedom).
    Returns parsed JSON dict or empty dict on failure.
    """
    import json

    cmd = [
        "docker",
        "exec",
        runner_container,
        "curl",
        "-s",
        "--connect-timeout",
        "5",
        "--max-time",
        "10",
        "--socks5-hostname",
        f"{proxy_client_name}:{socks_port}",
        target_url,
    ]
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0:
        log(f"Curl through VPN failed (exit {res.returncode}): {res.stderr}", "error")
        return {}

    try:
        data = json.loads(res.stdout.strip())
        return data
    except Exception as e:
        log(f"Failed to parse echo server JSON response: {e}\nRaw output:\n{res.stdout}", "error")
        return {}

def prepare_test_repo(*overlay_components: str) -> str:
    """
    Creates a merged copy of the repo with test overrides applied.
    
    Args:
        overlay_components: "panel", "sub-server", or both
    
    Returns:
        Path to the merged temporary directory
    """
    import shutil
    import tempfile
    import atexit
    import os
    
    working_dir = os.path.join(REPO_ROOT, "tests", "working")
    os.makedirs(working_dir, exist_ok=True)
    
    merged = tempfile.mkdtemp(prefix="3xui-test-", dir=working_dir)
    atexit.register(lambda: shutil.rmtree(merged, ignore_errors=True))
    
    def _ignore(dir_path, contents):
        ignored = set(shutil.ignore_patterns(
            '.git', '__pycache__', '*.pyc', 'setup_backup.yml', '.python_env'
        )(dir_path, contents))
        rel = os.path.relpath(dir_path, REPO_ROOT)
        if rel == 'tests':
            ignored.update({'working', '.cache'})
        elif rel == 'panel':
            ignored.add('static')
        return list(ignored)

    # Copy production repo (excluding heavy/irrelevant dirs)
    shutil.copytree(REPO_ROOT, merged, dirs_exist_ok=True, ignore=_ignore)
    
    # Apply overlays
    for component in overlay_components:
        override_src = os.path.join(REPO_ROOT, "tests", "overrides", component)
        override_dst = os.path.join(merged, component)
        if os.path.isdir(override_src):
            shutil.copytree(override_src, override_dst, dirs_exist_ok=True)
    
    return merged
