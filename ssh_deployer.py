import asyncio
import base64
import hashlib
import io
import json
import os
import re
import shlex
import sys
import tarfile
import time
from dataclasses import dataclass
from typing import Callable, Dict, Any, Optional, List, Tuple

import decoy_manager

from constants import REMOTE_DIR
from core.ssh_client import SSHDeployer
from deployers.strategies import STRATEGIES, RunContext

REPO_ROOT = os.path.dirname(os.path.abspath(globals()["__file__"])) if globals().get("__file__") else os.path.abspath(os.path.dirname(sys.argv[0]) if sys.argv and sys.argv[0] else os.getcwd())

@dataclass
class NodeConfig:
    """Connection + deployment parameters for a remote node (Phase C4 of REFACTORING.md)."""
    host: str
    port: int
    user: str
    password: str
    key_data: str
    env_vars: Dict[str, str]
    cancel_check: Optional[Callable[[], bool]] = None
    bundle_source_dir: Optional[str] = None
    decoy_files: Optional[Dict[str, bytes]] = None


@dataclass
class ServerConnection:
    """Unified SSH connection params per role (Phase F1 of REFACTORING.md).

    Reads ``<prefix>_host/_port/_user/_password/_key`` from a flat form config
    (the ``*_auth_type`` keys are role-specific and handled by callers).
    """
    host: str
    port: Any
    user: str
    password: str
    key_data: str

    @classmethod
    def from_config(cls, config: Dict[str, Any], prefix: str) -> "ServerConnection":
        return cls(
            host=str(config.get(f"{prefix}_host", "") or "").strip(),
            port=config.get(f"{prefix}_port"),
            user=str(config.get(f"{prefix}_user", "") or "").strip(),
            password=str(config.get(f"{prefix}_password", "") or ""),
            key_data=str(config.get(f"{prefix}_key", "") or ""),
        )

    def validate(self, label: str) -> Optional[str]:
        """Return the first validation error for ``label`` or ``None``."""
        if not self.host:
            return f"Укажите домен {label}"
        try:
            p = int(self.port or 22)
            if p <= 0 or p > 65535:
                return f"Укажите корректный SSH порт {label} (1-65535)"
        except (ValueError, TypeError):
            return f"Укажите корректный SSH порт {label}"
        if not self.user:
            return f"Укажите SSH пользователя {label}"
        if not self.password and not self.key_data:
            return f"Укажите SSH пароль или ключ {label}"
        return None

def get_bundle_bytes(source_dir: str | None = None, decoy_files: Dict[str, bytes] | None = None) -> bytes:
    buf = io.BytesIO()
    repo_dir = source_dir or REPO_ROOT
    decoy_prefix = os.path.join("common", "templates", "nginx-decoy", "html")
    with tarfile.open(fileobj=buf, mode='w:gz') as tar:
        for root, dirs, files in os.walk(repo_dir):
            if '.git' in root or '.python_env' in root or '__pycache__' in root or (os.sep + 'panel' + os.sep + 'static') in root or 'backups_panel' in root or 'backups_sub_server' in root or (os.sep + '.cache') in root or (os.sep + 'deployers') in root or (os.sep + 'core') in root:
                continue
            for file in files:
                if file.endswith('.pyc') or file in ('setup_backup.yml', 'sub-server.log', 'servers.json', 'force-subs.yml', 'nodes.json', 'subs.yml'):
                    continue
                full_path = os.path.join(root, file)
                rel_path = os.path.relpath(full_path, repo_dir)
                if decoy_files is not None and (rel_path == decoy_prefix or rel_path.startswith(decoy_prefix + os.sep)):
                    continue
                tar.add(full_path, arcname=rel_path)

        if decoy_files:
            for d_rel, d_bytes in decoy_files.items():
                arc_path = os.path.join("common", "templates", "nginx-decoy", "html", d_rel).replace(os.sep, "/")
                ti = tarfile.TarInfo(name=arc_path)
                ti.size = len(d_bytes)
                ti.mtime = int(time.time())
                ti.mode = 0o644
                tar.addfile(ti, io.BytesIO(d_bytes))

    return buf.getvalue()

def parse_deployment_results(output_text: str) -> Tuple[str, List[Dict[str, str]]]:
    lines = output_text.splitlines()
    start_idx = -1
    end_idx = -1
    for i, line in enumerate(lines):
        line = line.strip()
        if "===RESULT_JSON_START===" in line:
            start_idx = i
        elif "===RESULT_JSON_END===" in line:
            end_idx = i
            break
            
    if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
        json_content = "\n".join(lines[start_idx + 1:end_idx]).strip()
        try:
            data = json.loads(json_content)
            xui_url = data.get("panel_url", "")
            clients = []
            for c in data.get("clients", []):
                clients.append({
                    "name": c.get("name", ""),
                    "sub_url": c.get("sub_url", ""),
                    "tcp_url": c.get("tcp_url", ""),
                    "xhttp_url": c.get("xhttp_url", "")
                })
            return xui_url, clients
        except Exception:
            pass

    return "", []


def derive_sub_path(secret: str) -> str:
    if not secret or not str(secret).strip():
        return ""
    return hashlib.md5(f"{secret.strip()}-sub".encode('utf-8')).hexdigest()[:16]


def derive_sub_server_path(secret: str) -> str:
    if not secret or not str(secret).strip():
        return ""
    return hashlib.md5(secret.strip().encode('utf-8')).hexdigest()[:16]


# ---------------------------------------------------------------------------
# Backend URL resolvers — overrideable entry-points for sub-server URLs.
# ---------------------------------------------------------------------------

def resolve_sub_server_urls(
    proxy_sub_url: str,
    freedom_sub_url: str,
) -> Tuple[str, str, Dict[str, str]]:
    """Resolve backend subscription URLs for the sub-server.
    Returns (russian_url, freedom_url, extra_env)."""
    return proxy_sub_url, freedom_sub_url, {}


def extract_domain_from_url(url: str) -> str:
    if not url:
        return ""
    u = re.sub(r'^[a-zA-Z]+://', '', url.strip())
    return u.split('/')[0].split(':')[0].strip()


# ---------------------------------------------------------------------------
# Remote scripts (kept in common/remote_scripts/*.sh so they can be
# shellchecked; loaded verbatim here). Written as plain strings, not
# f-strings: variables are resolved by the remote shell at runtime.
# ---------------------------------------------------------------------------

def _read_remote_script(name: str) -> str:
    with open(os.path.join(REPO_ROOT, "common", "remote_scripts", name), "r", encoding="utf-8") as f:
        return f.read()


# Backups created by the pre-"panel/" repo layout reference the caddy build
# context `./templates/docker-compose` (relative to --project-directory). The
# current bundle keeps templates under panel/templates/, so as a LEGACY FALLBACK
# only (when the compose file actually references the old context) bridge the
# legacy path with a symlink before any `docker compose` run that may rebuild.
LEGACY_TEMPLATES_SYMLINK_CMD = _read_remote_script("legacy_templates_symlink.sh")


# Legacy fallback for recovery: pre-"panel/" backups build the caddy image from
# ./templates/docker-compose (source build, needs the Go toolchain + takes ~70s).
# Modern deployments pull the published ghcr.io/honmiv/caddy-l4:latest image. When
# the restored compose references the old build context, rewrite the caddy service
# to use the published image instead, so recovery needs no build context at all.
LEGACY_COMPOSE_REWRITE_CMD = _read_remote_script("legacy_compose_rewrite.sh")


# Runs on the recovered VPS AFTER `docker compose up -d`. Rewrites the domain
# inside the running 3x-UI panel through its HTTP API (CSRF + cookie auth,
# docker exec + curl + jq), so no SQLite access is needed. Replaces serverName /
# client `add` / externalProxy dest / subURI wherever the old domain appears.
PANEL_DOMAIN_REWRITE_SCRIPT = _read_remote_script("panel_domain_rewrite.sh")


async def _perform_remote_backup(
    deployer: SSHDeployer,
    backup_name: str,
    log: Callable[[str, str], None],
    target: str = "panel"
) -> tuple[bool, str, float]:
    """Create a backup archive on the remote server, download it locally via SCP, and clean up.

    Args:
        deployer: SSHDeployer instance.
        backup_name: Target filename for the backup archive.
        log: Log callback.
        target: "panel" (default) or "sub_server".

    Returns:
        (success, local_backup_path, file_size_mb)
    """
    is_sub = (target == "sub_server")
    folder_name = "backups_sub_server" if is_sub else "backups_panel"
    desc_label = "sub-server config" if is_sub else "panel"

    repo_root = REPO_ROOT
    backups_dir = os.path.join(repo_root, folder_name)
    os.makedirs(backups_dir, exist_ok=True)
    local_backup_path = os.path.join(backups_dir, backup_name)

    log(f"Creating {desc_label} backup archive on remote server...", "info")

    if is_sub:
        remote_script = (
            "set -e\n"
            "WORK_DIR=\"/opt/3x-ui-bootstRUp\"\n"
            "if [ ! -d \"$WORK_DIR\" ]; then\n"
            "  if [ -d \"./working\" ]; then WORK_DIR=\".\"; else WORK_DIR=\"$(pwd)\"; fi\n"
            "fi\n"
            "cd \"$WORK_DIR\"\n"
            "rm -rf /tmp/backup_stage /tmp/server_backup.tar.gz\n"
            "mkdir -p /tmp/backup_stage/working\n"
            "[ -f \"sub-server/nodes.json\" ] && cp \"sub-server/nodes.json\" /tmp/backup_stage/nodes.json || true\n"
            "[ -f \"sub-server/subs.yml\" ] && cp \"sub-server/subs.yml\" /tmp/backup_stage/subs.yml || true\n"
            "[ -f \"sub-server/force-subs.yml\" ] && cp \"sub-server/force-subs.yml\" /tmp/backup_stage/force-subs.yml || true\n"
            "[ -f \"working/caddy/Caddyfile\" ] && cp \"working/caddy/Caddyfile\" /tmp/backup_stage/working/Caddyfile || true\n"
            "[ -f \"working/docker-compose/docker-compose.yml\" ] && cp \"working/docker-compose/docker-compose.yml\" /tmp/backup_stage/working/docker-compose.yml || true\n"
            "[ -d \".caddy_data\" ] && cp -r \".caddy_data\" /tmp/backup_stage/.caddy_data || true\n"
            "tar -czf /tmp/server_backup.tar.gz -C /tmp/backup_stage .\n"
            "rm -rf /tmp/backup_stage\n"
        )
    else:
        remote_script = (
            "set -e\n"
            "WORK_DIR=\"/opt/3x-ui-bootstRUp\"\n"
            "if [ ! -d \"$WORK_DIR\" ]; then\n"
            "  if [ -d \"./working\" ]; then WORK_DIR=\".\"; else WORK_DIR=\"$(pwd)\"; fi\n"
            "fi\n"
            "cd \"$WORK_DIR\"\n"
            "rm -rf /tmp/backup_stage /tmp/server_backup.tar.gz\n"
            "if [ -f \"panel_backup.sh\" ]; then\n"
            "  bash panel_backup.sh /tmp/backup_stage\n"
            "else\n"
            "  mkdir -p /tmp/backup_stage\n"
            "  [ -d \"working/3x-ui\" ] && cp -r working/3x-ui /tmp/backup_stage/3x-ui || true\n"
            "  [ -d \"working/3xui\" ] && cp -r working/3xui /tmp/backup_stage/3xui || true\n"
            "  [ -d \"working/docker-compose\" ] && cp -r working/docker-compose /tmp/backup_stage/docker-compose || true\n"
            "  [ -d \"working/nginx-decoy\" ] && cp -r working/nginx-decoy /tmp/backup_stage/nginx-decoy || true\n"
            "  [ -d \"working/caddy\" ] && cp -r working/caddy /tmp/backup_stage/caddy || true\n"
            "fi\n"
            "tar -czf /tmp/server_backup.tar.gz -C /tmp/backup_stage .\n"
            "rm -rf /tmp/backup_stage\n"
        )

    rc, out = await deployer.exec_command(f"bash -c {shlex.quote(remote_script)}", lambda m: log(m, "info"))
    if rc != 0:
        log(f"[ERROR] Remote backup creation failed: {out}", "error")
        return False, "", 0.0

    log(f"⬇️ Downloading backup archive via SCP to ./{folder_name}/{backup_name}...", "info")
    rc_scp, scp_out = await deployer.download_file("/tmp/server_backup.tar.gz", local_backup_path, lambda m: log(m, "info"))

    await deployer.exec_command("rm -f /tmp/server_backup.tar.gz")

    if rc_scp != 0 or not os.path.exists(local_backup_path):
        log(f"[ERROR] SCP download failed: {scp_out}", "error")
        return False, "", 0.0

    file_size_bytes = os.path.getsize(local_backup_path)
    file_size_mb = round(file_size_bytes / (1024 * 1024), 2)

    return True, local_backup_path, file_size_mb


async def _deploy_node(node: NodeConfig, log: Callable[[str, str], None]) -> tuple[bool, str]:
    host = node.host
    port = node.port
    remote_dir = REMOTE_DIR
    async with SSHDeployer(host, port, node.user, node.password, node.key_data, cancel_check=node.cancel_check) as deployer:
        log(f"Connecting to {host}:{port}...", "info")
        ok, msg = await deployer.test_connection()
        if not ok:
            log(f"SSH test failed for {host}: {msg}", "error")
            return False, ""

        log(f"Syncing local files to {host}...", "info")
        bundle_bytes = get_bundle_bytes(source_dir=node.bundle_source_dir, decoy_files=node.decoy_files)
        sync_cmd = f"mkdir -p {remote_dir} && tar -xzf - -C {remote_dir}"
        rc, sync_out = await deployer.exec_command(sync_cmd, lambda m: log(m, "info"), stdin_data=bundle_bytes)
        if rc != 0:
            log(f"[ERROR] Failed to transfer files to {host}: {sync_out}", "error")
            return False, ""

        log(f"Executing setup.sh script on {host}...", "info")
        
        env_str_parts = []
        for k, v in node.env_vars.items():
            if v is not None:
                env_str_parts.append(f"{k}={shlex.quote(str(v))}")
        env_str = " ".join(env_str_parts)
        remote_cmd = f"cd {shlex.quote(remote_dir)} && {env_str} bash panel/setup.sh"
        rc, out = await deployer.exec_command(remote_cmd, lambda m: log(m, "info"))
        if rc == 0:
            return True, out
        return False, out

def _sub_server_sync_cmd(remote_dir: str, preserve: bool) -> str:
    """Build the remote command that syncs the sub-server repo bundle.

    When ``preserve`` is True, the runtime state files (nodes.json and
    force-subs.yml; plus the legacy subs.yml if present) are backed up before
    the bundle is extracted and restored afterwards, so refreshing the tool
    scripts never clobbers remote client/override data.
    """
    backup = (
        f"for f in subs.yml force-subs.yml nodes.json sub-server.log; do "
        f"if [ -f {remote_dir}/sub-server/$f ]; then "
        f"cp {remote_dir}/sub-server/$f /tmp/sub-server-$f.bak; fi; "
        f"done"
    ) if preserve else "true"
    restore = (
        f"for f in subs.yml force-subs.yml nodes.json sub-server.log; do "
        f"if [ -f /tmp/sub-server-$f.bak ]; then "
        f"cp /tmp/sub-server-$f.bak {remote_dir}/sub-server/$f; rm -f /tmp/sub-server-$f.bak; fi; "
        f"done"
    ) if preserve else "true"
    return (
        f"mkdir -p {remote_dir} && "
        f"{backup} && "
        f"tar -xzf - -C {remote_dir} && "
        f"{restore}"
    )

async def _deploy_sub_server(node: NodeConfig, log: Callable[[str, str], None]) -> tuple[bool, str]:
    host = node.host
    port = node.port
    remote_dir = REMOTE_DIR
    async with SSHDeployer(host, port, node.user, node.password, node.key_data, cancel_check=node.cancel_check) as deployer:
        log(f"Connecting to Subscription Server on {host}:{port}...", "info")
        ok, msg = await deployer.test_connection()
        if not ok:
            log(f"SSH test failed for Subscription Server {host}: {msg}", "error")
            return False, ""

        log(f"Syncing local files to Subscription Server {host}...", "info")
        bundle_bytes = get_bundle_bytes(source_dir=node.bundle_source_dir, decoy_files=node.decoy_files)
        sync_cmd = _sub_server_sync_cmd(remote_dir, preserve=(node.env_vars.get("UPDATE_SUB_SERVER", "") == "1"))
        rc, sync_out = await deployer.exec_command(sync_cmd, lambda m: log(m, "info"), stdin_data=bundle_bytes)
        if rc != 0:
            log(f"[ERROR] Failed to transfer files to Subscription Server {host}: {sync_out}", "error")
            return False, ""

        log(f"Executing sub-server/setup.sh script on {host}...", "info")
        env_str_parts = []
        for k, v in node.env_vars.items():
            if v is not None:
                env_str_parts.append(f"{k}={shlex.quote(str(v))}")
        env_str = " ".join(env_str_parts)
        remote_cmd = f"cd {shlex.quote(remote_dir)} && {env_str} bash sub-server/setup.sh"
        rc, out = await deployer.exec_command(remote_cmd, lambda m: log(m, "info"))
        if rc == 0:
            return True, out
        return False, out

async def _probe_remote_http_port(
    host: str,
    target_port: int,
    current_port: int,
    user: str,
    password: str,
    key_data: str,
    log: Callable[[str, str], None],
    cancel_check: Optional[Callable[[], bool]] = None
) -> Tuple[bool, str]:
    log(f"Запуск тестового HTTP-сервера на {host}:{target_port} для предварительной проверки доступности порта...", "info")

    script = f"""set -e
PORT="{target_port}"

# 1. Firewalls & SELinux for target port
if command -v ufw >/dev/null 2>&1; then
    if ufw status 2>/dev/null | grep -qw "active"; then
        ufw allow "$PORT"/tcp comment "Custom SSH Port" 2>/dev/null || true
    fi
fi
if command -v firewall-cmd >/dev/null 2>&1 && systemctl is-active --quiet firewalld 2>/dev/null; then
    firewall-cmd --add-port="$PORT"/tcp --permanent 2>/dev/null || true
    firewall-cmd --reload 2>/dev/null || true
fi
if command -v iptables >/dev/null 2>&1; then
    if ! iptables -C INPUT -p tcp --dport "$PORT" -j ACCEPT 2>/dev/null; then
        iptables -I INPUT 1 -p tcp --dport "$PORT" -j ACCEPT 2>/dev/null || true
    fi
fi
if command -v ip6tables >/dev/null 2>&1; then
    if ! ip6tables -C INPUT -p tcp --dport "$PORT" -j ACCEPT 2>/dev/null; then
        ip6tables -I INPUT 1 -p tcp --dport "$PORT" -j ACCEPT 2>/dev/null || true
    fi
fi
if command -v nft >/dev/null 2>&1 && systemctl is-active --quiet nftables 2>/dev/null; then
    if nft list ruleset 2>/dev/null | grep -q "chain input"; then
        nft add rule inet filter input tcp dport "$PORT" accept 2>/dev/null || true
    fi
fi
if command -v getenforce >/dev/null 2>&1 && [ "$(getenforce)" != "Disabled" ]; then
    if command -v semanage >/dev/null 2>&1; then
        semanage port -a -t ssh_port_t -p tcp "$PORT" 2>/dev/null || \\
        semanage port -m -t ssh_port_t -p tcp "$PORT" 2>/dev/null || true
    fi
fi

PY_BIN="$(command -v python3 || command -v python || true)"
if [ -z "$PY_BIN" ]; then
    echo "PROBE_HTTP_NO_PYTHON"
    exit 1
fi

$PY_BIN -c "
import http.server, socketserver, sys

class ProbeHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        body = b'BOOTSTRUP_HTTP_OK\\n'
        self.send_response(200)
        self.send_header('Content-Type', 'text/plain')
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Connection', 'close')
        self.end_headers()
        self.wfile.write(body)
        self.wfile.flush()
    def log_message(self, format, *args):
        pass

class ReusableTCPServer(socketserver.TCPServer):
    allow_reuse_address = True

try:
    with ReusableTCPServer(('0.0.0.0', $PORT), ProbeHandler) as httpd:
        httpd.timeout = 15
        print('PROBE_HTTP_LISTENING', flush=True)
        httpd.handle_request()
        print('PROBE_HTTP_DONE', flush=True)
except Exception as e:
    print(f'PROBE_HTTP_ERROR: {{e}}', flush=True)
    sys.exit(1)
"
"""

    ready_event = asyncio.Event()
    probe_error: list[str] = []

    def on_output(line: str):
        line = line.strip()
        if "PROBE_HTTP_LISTENING" in line:
            ready_event.set()
        elif "PROBE_HTTP_ERROR" in line or "PROBE_HTTP_NO_PYTHON" in line:
            probe_error.append(line)

    async with SSHDeployer(host, current_port, user, password, key_data, cancel_check=cancel_check) as deployer:
        cmd_str = f"bash -c {shlex.quote(script)}"
        server_task = asyncio.create_task(deployer.exec_command(cmd_str, on_output))

        try:
            await asyncio.wait_for(ready_event.wait(), timeout=12.0)
        except asyncio.TimeoutError:
            if server_task.done():
                rc, out = server_task.result()
                err = " ".join(probe_error) or out or "Не удалось запустить тестовый HTTP-сервер"
                return False, f"Ошибка запуска тестового сервера: {err}"
            server_task.cancel()
            return False, "Таймаут ожидания запуска тестового HTTP-сервера на сервере"

        log(f"Тестовый HTTP-сервер активен. Отправка запроса на http://{host}:{target_port}/...", "info")
        http_ok = False
        http_err = ""
        try:
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(host, target_port),
                timeout=7.0
            )
            req = f"GET /probe HTTP/1.1\r\nHost: {host}\r\nConnection: close\r\n\r\n".encode("utf-8")
            writer.write(req)
            await writer.drain()
            resp = b""
            while True:
                try:
                    chunk = await asyncio.wait_for(reader.read(1024), timeout=4.0)
                except asyncio.TimeoutError:
                    break
                if not chunk:
                    break
                resp += chunk
                if b"BOOTSTRUP_HTTP_OK" in resp:
                    break
            writer.close()
            try:
                await asyncio.wait_for(writer.wait_closed(), timeout=2.0)
            except Exception:
                pass
            if b"BOOTSTRUP_HTTP_OK" in resp:
                http_ok = True
            else:
                http_err = f"Неожиданный ответ сервера: {resp[:100]!r}"
        except ConnectionRefusedError:
            http_err = "Соединение сброшено (Connection refused). Порт закрыт фаерволом ОС или хостинга"
        except asyncio.TimeoutError:
            http_err = "Превышено время ожидания ответа (Connection timed out). Пакеты блокируются фаерволом хостинга"
        except Exception as e:
            http_err = f"Сетевая ошибка: {str(e)}"

        try:
            await asyncio.wait_for(server_task, timeout=5.0)
        except Exception:
            if not server_task.done():
                server_task.cancel()

        if http_ok:
            log(f"✅ Внешнее подключение к тестовому HTTP-серверу на порту {target_port} успешно! Порт открыт.", "success")
            await asyncio.sleep(0.5)
            return True, ""
        else:
            return False, http_err

async def _change_remote_ssh_port(
    host: str,
    current_port: int,
    new_port: int,
    user: str,
    password: str,
    key_data: str,
    log: Callable[[str, str], None],
    cancel_check: Optional[Callable[[], bool]] = None
) -> bool:
    if not host:
        return False

    if current_port != new_port:
        log(f"Начало настройки смены SSH-порта на {host}: {current_port} ➔ {new_port}...", "info")
        probe_ok, probe_err = await _probe_remote_http_port(
            host, new_port, current_port, user, password, key_data, log, cancel_check
        )
        if not probe_ok:
            log(f"❌ Предварительная проверка не удалась: порт {new_port} на {host} недоступен извне!", "error")
            log(f"   Причина: {probe_err}", "warning")
            log(f"🛡️ Конфигурация SSH НЕ была изменена во избежание потери доступа. Сервер продолжает работать на порту {current_port}.", "warning")
            log(f"💡 Проверьте настройки фаервола в панели управления вашего хостинга (раздел Firewall / Security Groups).", "info")
            return False
        log(f"Смена SSH-порта на {host}: {current_port} ➔ {new_port} (со скрытием баннеров)...", "info")
    else:
        log(f"Настройка SSH на {host}: порт {new_port} (применение скрытия баннеров и проверка безопасности)...", "info")

    script = f"""export PATH="/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin:$PATH"
NEW_PORT="{new_port}"
CURRENT_PORT="{current_port}"

echo "[SSH-SETUP] Шаг 1: Проверка освобождения порта..."
fuser -k -n tcp "$NEW_PORT" 2>/dev/null || true

echo "[SSH-SETUP] Шаг 2: Создание drop-in конфигурации /etc/ssh/sshd_config.d/99-custom-ssh.conf..."
mkdir -p /etc/ssh/sshd_config.d
cat <<'EOF_SSH' > /etc/ssh/sshd_config.d/99-custom-ssh.conf
Port {new_port}
Banner none
EOF_SSH

echo "[SSH-SETUP] Шаг 3: Проверка поддержки DebianBanner..."
SSHD_BIN="$(command -v sshd || echo "/usr/sbin/sshd")"
if $SSHD_BIN -T 2>/dev/null | grep -qi "^debianbanner"; then
    echo "DebianBanner no" >> /etc/ssh/sshd_config.d/99-custom-ssh.conf
    echo "[SSH-SETUP] -> DebianBanner no добавлен."
else
    echo "[SSH-SETUP] -> DebianBanner не поддерживается или отключен."
fi

echo "[SSH-SETUP] Шаг 4: Обновление /etc/ssh/sshd_config..."
if [ -f /etc/ssh/sshd_config ]; then
    if grep -qE "^[# ]*Port " /etc/ssh/sshd_config; then
        sed -i -E "s/^[# ]*Port .*/Port $NEW_PORT/" /etc/ssh/sshd_config
        echo "[SSH-SETUP] -> Порт в /etc/ssh/sshd_config обновлен на $NEW_PORT"
    else
        echo "Port $NEW_PORT" >> /etc/ssh/sshd_config
        echo "[SSH-SETUP] -> Добавлен Port $NEW_PORT в /etc/ssh/sshd_config"
    fi
fi

echo "[SSH-SETUP] Шаг 5: Проверка и настройка systemd ssh.socket..."
IS_SOCK=0
if systemctl is-active --quiet ssh.socket 2>/dev/null || systemctl is-enabled --quiet ssh.socket 2>/dev/null; then
    IS_SOCK=1
    echo "[SSH-SETUP] -> Обнаружен активный/включенный ssh.socket, настраиваем listen.conf..."
    mkdir -p /etc/systemd/system/ssh.socket.d
    cat <<'EOF_SOCK' > /etc/systemd/system/ssh.socket.d/listen.conf
[Socket]
ListenStream=
ListenStream=0.0.0.0:{new_port}
EOF_SOCK
    if [ -f /proc/net/if_inet6 ] && grep -qv "^#" /proc/net/if_inet6 2>/dev/null; then
        if python3 -c "import socket; s=socket.socket(socket.AF_INET6, socket.SOCK_STREAM); s.close()" 2>/dev/null; then
            cat <<'EOF_SOCK6' >> /etc/systemd/system/ssh.socket.d/listen.conf
ListenStream=[::]:{new_port}
BindIPv6Only=ipv6-only
EOF_SOCK6
            echo "[SSH-SETUP] -> Добавлен IPv6 ListenStream=[::]:{new_port}"
        fi
    fi
else
    echo "[SSH-SETUP] -> ssh.socket не используется (используется традиционная служба ssh/sshd)."
    rm -rf /etc/systemd/system/ssh.socket.d 2>/dev/null || true
fi

echo "[SSH-SETUP] Шаг 6: Тестирование валидности конфигурации ($SSHD_BIN -t)..."
if ! $SSHD_BIN -t 2>/tmp/sshd_t_err.txt; then
    echo "[ERROR] Ошибка валидации конфигурации sshd -t:"
    cat /tmp/sshd_t_err.txt 2>/dev/null || true
    rm -f /tmp/sshd_t_err.txt
    rm -f /etc/ssh/sshd_config.d/99-custom-ssh.conf
    rm -rf /etc/systemd/system/ssh.socket.d
    exit 1
fi
rm -f /tmp/sshd_t_err.txt
echo "[SSH-SETUP] -> Конфигурация sshd валидна."

echo "[SSH-SETUP] Шаг 7: Запуск сторожевого демона (Watchdog 20s) и перезапуск SSH..."
rm -f /tmp/ssh_switch_confirmed
cat <<'EOF_WD' > /tmp/.ssh_watchdog.sh
#!/bin/bash
NEW_P="$1"
FALLBACK_P="$2"
IS_SK="$3"
TIMEOUT=20

exec > /tmp/ssh_watchdog.log 2>&1
echo "[WATCHDOG] Запущен: $(date). Порт: $NEW_P, откат: $FALLBACK_P, таймаут: ${{TIMEOUT}}с"

sleep 1.5

echo "[WATCHDOG] Выполнение systemctl daemon-reload..."
systemctl daemon-reload 2>&1 || true

if [ "$IS_SK" = "1" ]; then
    echo "[WATCHDOG] Перезапуск ssh.socket..."
    systemctl restart ssh.socket 2>&1 || true
else
    echo "[WATCHDOG] Перезапуск ssh service..."
    systemctl restart ssh 2>&1 || systemctl restart sshd 2>&1 || service ssh restart 2>&1 || service sshd restart 2>&1 || true
fi

echo "[WATCHDOG] SSH перезапущен на порт $NEW_P. Ожидание файла подтверждения /tmp/ssh_switch_confirmed..."

CONFIRMED=0
for i in $(seq 1 $TIMEOUT); do
    if [ -f /tmp/ssh_switch_confirmed ]; then
        echo "[WATCHDOG] Подтверждение получено на ${{i}}-й секунде! Успешный переход на порт $NEW_P."
        rm -f /tmp/ssh_switch_confirmed
        CONFIRMED=1
        break
    fi
    sleep 1
done

if [ "$CONFIRMED" -eq 0 ]; then
    echo "[WATCHDOG] ⚠️ ВНИМАНИЕ: Таймаут ${{TIMEOUT}}с истёк без подтверждения! Запуск автономного отката на порт $FALLBACK_P..."
    rm -f /etc/ssh/sshd_config.d/99-custom-ssh.conf
    rm -rf /etc/systemd/system/ssh.socket.d
    if [ -f /etc/ssh/sshd_config ]; then
        sed -i -E "s/^[# ]*Port .*/Port $FALLBACK_P/" /etc/ssh/sshd_config 2>/dev/null || true
    fi
    systemctl daemon-reload 2>&1 || true
    if [ "$IS_SK" = "1" ]; then
        echo "[WATCHDOG] Откат: перезапуск ssh.socket..."
        systemctl restart ssh.socket 2>&1 || true
    else
        echo "[WATCHDOG] Откат: перезапуск ssh service..."
        systemctl restart ssh 2>&1 || systemctl restart sshd 2>&1 || service ssh restart 2>&1 || service sshd restart 2>&1 || true
    fi
    echo "[WATCHDOG] 🔄 Автономный откат на порт $FALLBACK_P успешно завершён в $(date)."
fi
EOF_WD
chmod +x /tmp/.ssh_watchdog.sh

if command -v systemd-run >/dev/null 2>&1 && [ -d /run/systemd/system ]; then
    echo "[SSH-SETUP] -> Запуск сторожевого демона через systemd-run..."
    systemctl stop ssh-port-watchdog 2>/dev/null || true
    systemctl reset-failed ssh-port-watchdog 2>/dev/null || true
    systemd-run --unit=ssh-port-watchdog /bin/bash /tmp/.ssh_watchdog.sh "$NEW_PORT" "$CURRENT_PORT" "$IS_SOCK" || \
    nohup /bin/bash /tmp/.ssh_watchdog.sh "$NEW_PORT" "$CURRENT_PORT" "$IS_SOCK" </dev/null >/dev/null 2>&1 &
else
    echo "[SSH-SETUP] -> Запуск сторожевого демона через nohup..."
    nohup /bin/bash /tmp/.ssh_watchdog.sh "$NEW_PORT" "$CURRENT_PORT" "$IS_SOCK" </dev/null >/dev/null 2>&1 &
fi
echo "[SSH-SETUP] -> Сторожевой демон активирован. Скрипт завершен успешно."
"""

    async with SSHDeployer(host, current_port, user, password, key_data, cancel_check=cancel_check) as deployer:
        rc, out = await deployer.exec_command(f"bash -c {shlex.quote(script)}", lambda m: log(m, "info"))
        if rc != 0:
            err_details = out.strip() if out.strip() else f"Код ошибки {rc}"
            log(f"⚠️ Ошибка при настройке SSH порта на {host}: {err_details}", "warning")
            return False

    # Wait for the watchdog to apply the restart
    log(f"Ожидание перезапуска SSH-сервиса и активация сторожевого таймера (20 сек)...", "info")

    # Verify by testing connection to the new port
    log(f"Проверка подключения SSH к {host}:{new_port}...", "info")
    verified = False
    last_msg = ""
    for attempt in range(1, 5):
        if cancel_check and cancel_check():
            break
        await asyncio.sleep(2.0)
        async with SSHDeployer(host, new_port, user, password, key_data, cancel_check=cancel_check) as verifier:
            ok, msg = await verifier.test_connection()
            if ok:
                verified = True
                # Confirm switch to the watchdog daemon!
                await verifier.exec_command("touch /tmp/ssh_switch_confirmed")
                log(f"✅ SSH успешно настроен на порту {new_port} и проверен! Автономный сторожевой таймер подтверждён.", "success")
                return True
            last_msg = msg
            if attempt < 4:
                log(f"   [Попытка {attempt}/4] Порт {new_port} пока не ответил ({msg}), ожидание...", "info")

    # If verification failed: perform safe rollback
    log(f"⚠️ Подключение к новому SSH-порту {new_port} не удалось ({last_msg}).", "warning")
    if current_port != new_port:
        log(f"⏳ На сервере {host} активен автономный сторожевой таймер (Watchdog).", "warning")
        log(f"🔄 Выполняется автоматический откат настроек SSH на порт {current_port}...", "info")
        rb_success = False
        try:
            async with SSHDeployer(host, current_port, user, password, key_data, cancel_check=cancel_check) as diag_deployer:
                _, diag_out = await diag_deployer.exec_command("cat /tmp/ssh_watchdog.log 2>/dev/null || true")
                if diag_out.strip():
                    log(f"📋 Диагностический лог сторожевого таймера на сервере:\n{diag_out.strip()}", "info")
                
                rollback_script = f"""export PATH="/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin:$PATH"
touch /tmp/ssh_switch_confirmed
systemctl stop ssh-port-watchdog 2>/dev/null || true
rm -f /etc/ssh/sshd_config.d/99-custom-ssh.conf
rm -rf /etc/systemd/system/ssh.socket.d
if [ -f /etc/ssh/sshd_config ]; then
    sed -i -E "s/^[# ]*Port .*/Port {current_port}/" /etc/ssh/sshd_config 2>/dev/null || true
fi
systemctl daemon-reload 2>/dev/null || true
if systemctl is-active --quiet ssh.socket 2>/dev/null || systemctl is-enabled --quiet ssh.socket 2>/dev/null; then
    systemctl restart ssh.socket 2>/dev/null || true
else
    systemctl restart ssh 2>/dev/null || systemctl restart sshd 2>/dev/null || service ssh restart 2>/dev/null || true
fi
"""
                rc, _ = await diag_deployer.exec_command(f"bash -c {shlex.quote(rollback_script)}")
                if rc == 0:
                    rb_test_ok, _ = await diag_deployer.test_connection()
                    if rb_test_ok:
                        rb_success = True
        except Exception:
            pass

        if rb_success:
            log(f"✅ Автоматический откат завершён: доступ к {host} на порту {current_port} сохранён.", "info")
        else:
            log(f"🛡️ Если связь через порт {current_port} прервалась, автономный сторожевой таймер на сервере автоматически восстановит порт {current_port} через 20 секунд.", "info")
            log(f"💡 Подождите до 20 секунд перед повторным подключением к порту {current_port}.", "info")

    return False

def validate_deployment_config(config: Dict[str, Any]) -> Tuple[bool, str]:
    mode = config.get("deploy_mode", "").strip()
    if not mode:
        mode = "cascade" if config.get("is_cascade", False) else "single"

    strategy = STRATEGIES.get(mode)
    if strategy is not None:
        err = strategy.validate(config)
        if err:
            return False, err
    else:
        return False, f"Неизвестный режим деплоя: {mode}"

    if config.get("change_ssh_port"):
        raw_port = config.get("new_ssh_port")
        try:
            p = int(raw_port)
            if p in [80, 443, 2053]:
                return False, f"Порт {p} зарезервирован для веб-сервера / панели"
            if p < 1024 or p > 65535:
                return False, "Новый SSH-порт должен быть числом от 1024 до 65535"
            if p in [80, 443, 2053]:
                return False, f"Порт {p} зарезервирован для веб-сервера / панели"
        except (ValueError, TypeError):
            return False, "Укажите корректный новый SSH-порт (число от 1024 до 65535)"

    return True, ""

async def run_deployment(config: Dict[str, Any], log_callback: Callable[[str, str], None], cancel_check: Optional[Callable[[], bool]] = None) -> Tuple[bool, Dict[str, Any]]:
    bundle_dir = config.get("bundle_source_dir")
    def log(msg: str, level: str = "info"):
        log_callback(msg, level)

    valid, err_msg = validate_deployment_config(config)
    if not valid:
        log(f"[ERROR] {err_msg}", "error")
        return False, {"error": err_msg}

    deploy_mode = config.get("deploy_mode", "").strip()
    if not deploy_mode:
        deploy_mode = "cascade" if config.get("is_cascade", False) else "single"

    change_ssh_port = bool(config.get("change_ssh_port"))
    new_ssh_port = None
    if change_ssh_port and config.get("new_ssh_port"):
        try:
            new_ssh_port = int(config.get("new_ssh_port"))
        except (ValueError, TypeError):
            new_ssh_port = None
    updated_ssh_ports: Dict[str, int] = {}

    xui_username = config.get("xui_username", "").strip()
    xui_password = config.get("xui_password", "").strip()
    xui_version = config.get("xui_version", "").strip()
    sub_secret = config.get("sub_secret", "").strip()

    def prepare_decoy_files(template_name: str, node_label: str = "") -> Optional[Dict[str, bytes]]:
        tpl = (template_name or "builtin").strip()
        label_prefix = f" [{node_label}]" if node_label else ""
        try:
            log(f"Preparing decoy camouflage template{label_prefix}: '{tpl}'...", "info")
            df = decoy_manager.get_decoy_bundle_files(tpl, randomize=True)
            log(f"[OK] Decoy site prepared{label_prefix} with unique anti-fingerprint build ({len(df)} files).", "info")
            return df
        except Exception as e:
            log(f"[WARN] Failed to prepare decoy '{tpl}'{label_prefix}: {e}. Falling back to builtin decoy.", "warn")
            try:
                return decoy_manager.get_decoy_bundle_files("builtin", randomize=True)
            except Exception:
                return None

    strategy = STRATEGIES.get(deploy_mode)
    if strategy is None:
        log(f"[ERROR] Неизвестный режим деплоя: {deploy_mode}", "error")
        return False, {"error": f"Неизвестный режим деплоя: {deploy_mode}"}

    ctx = RunContext(
        bundle_dir=bundle_dir,
        change_ssh_port=change_ssh_port,
        new_ssh_port=new_ssh_port,
        updated_ssh_ports=updated_ssh_ports,
        prepare_decoy_files=prepare_decoy_files,
    )
    return await strategy.run(config, log, cancel_check, ctx)
