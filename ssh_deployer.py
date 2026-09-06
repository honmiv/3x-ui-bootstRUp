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
import tempfile
import time
from typing import Callable, Dict, Any, Optional, List, Tuple

import decoy_manager

ANSI_ESCAPE = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
REPO_ROOT = os.path.dirname(os.path.abspath(globals()["__file__"])) if globals().get("__file__") else os.path.abspath(os.path.dirname(sys.argv[0]) if sys.argv and sys.argv[0] else os.getcwd())

def strip_ansi(text: str) -> str:
    return ANSI_ESCAPE.sub('', text)

def get_bundle_bytes(source_dir: str | None = None, decoy_files: Dict[str, bytes] | None = None) -> bytes:
    buf = io.BytesIO()
    repo_dir = source_dir or REPO_ROOT
    decoy_prefix = os.path.join("common", "templates", "nginx-decoy", "html")
    with tarfile.open(fileobj=buf, mode='w:gz') as tar:
        for root, dirs, files in os.walk(repo_dir):
            if '.git' in root or '.python_env' in root or '__pycache__' in root or (os.sep + 'panel' + os.sep + 'static') in root or 'backups_panel' in root or 'backups_sub_server' in root or (os.sep + '.cache') in root or (os.sep + 'deployers') in root:
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


# Backups created by the pre-"panel/" repo layout reference the caddy build
# context `./templates/docker-compose` (relative to --project-directory). The
# current bundle keeps templates under panel/templates/, so as a LEGACY FALLBACK
# only (when the compose file actually references the old context) bridge the
# legacy path with a symlink before any `docker compose` run that may rebuild.
LEGACY_TEMPLATES_SYMLINK_CMD = (
    "if [ -f \"$COMPOSE_FILE\" ] && grep -qE 'context:[[:space:]]+\\./templates' \"$COMPOSE_FILE\" 2>/dev/null \\\n"
    "   && [ -d panel/templates ] && [ ! -e templates ]; then\n"
    "  ln -s panel/templates templates\n"
    "fi\n"
)


# Legacy fallback for recovery: pre-"panel/" backups build the caddy image from
# ./templates/docker-compose (source build, needs the Go toolchain + takes ~70s).
# Modern deployments pull the published ghcr.io/honmiv/caddy-l4:latest image. When
# the restored compose references the old build context, rewrite the caddy service
# to use the published image instead, so recovery needs no build context at all.
LEGACY_COMPOSE_REWRITE_CMD = (
    "if [ -f \"$COMPOSE_FILE\" ] && grep -qE 'context:[[:space:]]+\\./templates' \"$COMPOSE_FILE\" 2>/dev/null; then\n"
    "  echo \"[INFO] Legacy caddy build context found in compose; using image ghcr.io/honmiv/caddy-l4:latest...\"\n"
    "  awk '\n"
    "    /^[[:space:]]*caddy:[[:space:]]*$/ { print; print \"    image: ghcr.io/honmiv/caddy-l4:latest\"; next }\n"
    "    /^[[:space:]]*build:[[:space:]]*$/ || /^[[:space:]]*context:[[:space:]]*\\.\\/templates/ || /^[[:space:]]*dockerfile:[[:space:]]*Dockerfile-caddy-l4/ { next }\n"
    "    { print }\n"
    "  ' \"$COMPOSE_FILE\" > \"$COMPOSE_FILE.tmp\" && mv \"$COMPOSE_FILE.tmp\" \"$COMPOSE_FILE\"\n"
    "fi\n"
)


# Runs on the recovered VPS AFTER `docker compose up -d`. Rewrites the domain
# inside the running 3x-UI panel through its HTTP API (CSRF + cookie auth,
# docker exec + curl + jq), so no SQLite access is needed. Replaces serverName /
# client `add` / externalProxy dest / subURI wherever the old domain appears.
PANEL_DOMAIN_REWRITE_SCRIPT = r'''#!/usr/bin/env bash
set -e

: "${RECOVERY_OLD_DOMAIN:?RECOVERY_OLD_DOMAIN is required}"
: "${RECOVERY_NEW_DOM:?RECOVERY_NEW_DOM is required}"
PANEL_USER="${RECOVERY_PANEL_USER:-admin}"
PANEL_PASS="${RECOVERY_PANEL_PASS:-admin}"

if [ "$RECOVERY_OLD_DOMAIN" = "$RECOVERY_NEW_DOM" ]; then
    echo "[INFO] Domain unchanged ($RECOVERY_OLD_DOMAIN); skipping 3x-ui API rewrite."
    exit 0
fi

cd /opt/3x-ui-bootstRUp
CADDY_FILE="working/caddy/Caddyfile"
if [ ! -f "$CADDY_FILE" ]; then
    echo "[ERROR] Caddyfile not found in recovered backup."
    exit 1
fi

WEB_BASE=$(grep -oE '@web_base_path path /[A-Za-z0-9_-]+' "$CADDY_FILE" | head -n 1 | awk '{print $3}' | tr -d '/' || true)
SUB_PATH=$(grep -oE '@sub_path path /[A-Za-z0-9_-]+' "$CADDY_FILE" | head -n 1 | awk '{print $3}' | tr -d '/' || true)
WEB_PORT=$(grep -oE 'reverse_proxy @web_base_path 3xui:[0-9]+' "$CADDY_FILE" | head -n 1 | sed 's/.*://' || true)

if [ -z "$WEB_PORT" ]; then
    echo "[ERROR] Could not determine 3x-ui web port from Caddyfile."
    exit 1
fi
echo "[INFO] Panel internal web port: ${WEB_PORT} (base path: /${WEB_BASE}/)"

COOKIE=/tmp/recovery_xui_cookie.txt

echo "[INFO] Waiting for 3x-ui panel to become ready..."
ready=""
for i in $(seq 1 90); do
    if docker exec 3xui sh -c "curl -s -o /dev/null http://127.0.0.1:${WEB_PORT}/" 2>/dev/null; then
        ready="1"
        break
    fi
    sleep 2
done
if [ -z "$ready" ]; then
    echo "[ERROR] 3x-ui panel did not become ready within 180s."
    exit 1
fi

docker exec 3xui sh -c "rm -f $COOKIE"

API_PREFIX=""
LOGIN_HTML=""
for prefix in "/${WEB_BASE}" ""; do
    LOGIN_HTML=$(docker exec 3xui sh -c "curl -fsS -c $COOKIE http://127.0.0.1:${WEB_PORT}${prefix}/" 2>/dev/null || true)
    if [ -n "$LOGIN_HTML" ]; then
        API_PREFIX="$prefix"
        break
    fi
done
if [ -z "$API_PREFIX" ]; then
    echo "[ERROR] Could not reach the 3x-ui login page inside the container."
    exit 1
fi
API_BASE="http://127.0.0.1:${WEB_PORT}${API_PREFIX}"
echo "[INFO] Reached panel at ${API_BASE}"

CSRF=$(printf '%s' "$LOGIN_HTML" | grep -oP 'csrf-token"\s+content="\K[^"]+' | head -n 1 || true)
if [ -z "$CSRF" ]; then
    echo "[ERROR] Could not obtain CSRF token from the login page."
    exit 1
fi

ENC_U=$(jq -rn --arg v "$PANEL_USER" '$v | @uri')
ENC_P=$(jq -rn --arg v "$PANEL_PASS" '$v | @uri')

docker exec 3xui sh -c "curl -fsS -b $COOKIE -c $COOKIE -H 'content-type: application/x-www-form-urlencoded; charset=UTF-8' -H 'x-csrf-token: $CSRF' --data 'username=${ENC_U}&password=${ENC_P}' ${API_BASE}/login" >/dev/null 2>&1 || true

PANEL_HTML=$(docker exec 3xui sh -c "curl -fsS -b $COOKIE -c $COOKIE ${API_BASE}/panel/" 2>/dev/null || true)
CSRF=$(printf '%s' "$PANEL_HTML" | grep -oP 'csrf-token"\s+content="\K[^"]+' | head -n 1 || true)
if [ -z "$CSRF" ]; then
    echo "[ERROR] 3x-ui panel login failed. Provide the panel admin credentials from the original deployment (default: admin/admin)."
    exit 1
fi
echo "[INFO] Authenticated to the 3x-ui panel."

# --- Update subURI (subscription base URL) ---
if [ -n "$SUB_PATH" ]; then
    echo "[INFO] Updating panel subURI -> https://${RECOVERY_NEW_DOM}/${SUB_PATH}/"
    SETTINGS=$(docker exec 3xui sh -c "curl -fsS -X POST -b $COOKIE -c $COOKIE -H 'accept: application/json' -H 'x-csrf-token: $CSRF' ${API_BASE}/panel/api/setting/all")
    SETTINGS_PAYLOAD=$(printf '%s' "$SETTINGS" | jq -r --arg uri "https://${RECOVERY_NEW_DOM}/${SUB_PATH}/" '.obj | .subURI = $uri | to_entries | map("\(.key)=\(.value | tostring | @uri)") | join("&")')
    printf '%s' "$SETTINGS_PAYLOAD" | docker exec -i 3xui sh -c 'cat > /tmp/recovery_setting_payload.txt'
    UPDATE_RESP=$(docker exec 3xui sh -c "curl -fsS -b $COOKIE -c $COOKIE -H 'content-type: application/x-www-form-urlencoded; charset=UTF-8' -H 'x-csrf-token: $CSRF' --data @/tmp/recovery_setting_payload.txt ${API_BASE}/panel/api/setting/update" 2>/dev/null || true)
    if printf '%s' "$UPDATE_RESP" | grep -q '"success":true'; then
        echo "[INFO] Panel settings updated (subURI)."
    else
        echo "[WARN] Panel settings update response: $UPDATE_RESP"
    fi
fi

# --- Rewrite domain in all inbounds (serverName / client add / externalProxy) ---
INBOUNDS=$(docker exec 3xui sh -c "curl -fsS -b $COOKIE -c $COOKIE -H 'accept: application/json' -H 'x-csrf-token: $CSRF' ${API_BASE}/panel/api/inbounds/list" 2>/dev/null || true)
INBOUND_COUNT=$(printf '%s' "$INBOUNDS" | jq -r '.obj | length' 2>/dev/null || echo 0)
if [ -n "$INBOUND_COUNT" ] && [ "$INBOUND_COUNT" -gt 0 ] 2>/dev/null; then
    echo "[INFO] Rewriting domain in ${INBOUND_COUNT} inbound(s)."
    i=0
    while [ "$i" -lt "$INBOUND_COUNT" ]; do
        OBJ=$(printf '%s' "$INBOUNDS" | jq -c --arg old "$RECOVERY_OLD_DOMAIN" --arg new "$RECOVERY_NEW_DOM" '.obj['"$i"'] | (def rec: if type == "object" then with_entries(.value |= rec) elif type == "array" then map(rec) elif type == "string" then (split($old) | join($new)) else . end; rec)')
        ID=$(printf '%s' "$OBJ" | jq -r '.id // empty')
        if [ -z "$ID" ]; then
            echo "[WARN] Inbound #$i has no id; skipped."
            i=$((i+1))
            continue
        fi
        PAYLOAD=$(printf '%s' "$OBJ" | jq -r 'to_entries | map("\(.key)=\(if (.value | type) == "object" or (.value | type) == "array" then (.value | tojson | @uri) else (.value | tostring | @uri) end)") | join("&")')
        printf '%s' "$PAYLOAD" | docker exec -i 3xui sh -c 'cat > /tmp/recovery_inbound_payload.txt'
        UPD_RESP=$(docker exec 3xui sh -c "curl -fsS -b $COOKIE -c $COOKIE -H 'content-type: application/x-www-form-urlencoded; charset=UTF-8' -H 'x-csrf-token: $CSRF' --data @/tmp/recovery_inbound_payload.txt ${API_BASE}/panel/api/inbounds/update/$ID" 2>/dev/null || true)
        if printf '%s' "$UPD_RESP" | grep -q '"success":true'; then
            echo "[INFO] Inbound $ID updated (serverName / client add / externalProxy)."
        else
            echo "[WARN] Inbound $ID update response: $UPD_RESP"
        fi
        i=$((i+1))
    done
else
    echo "[WARN] No inbounds found via API to update."
fi

# --- Restart Xray so the new config takes effect ---
echo "[INFO] Restarting Xray to apply the new domain..."
XRAY_OK=""
for XRAY_API in "panel/api/xray" "panel/xray"; do
    XR_RESP=$(docker exec 3xui sh -c "curl -fsS -X POST -b $COOKIE -c $COOKIE -H 'x-csrf-token: $CSRF' ${API_BASE}/${XRAY_API}/" 2>/dev/null || true)
    if printf '%s' "$XR_RESP" | grep -q '"success":true'; then
        XRAY_OK="1"
        break
    fi
done
if [ -n "$XRAY_OK" ]; then
    echo "[INFO] Xray restarted successfully."
else
    echo "[WARN] Could not restart Xray via API; a manual restart in the panel may be required."
fi

echo "[OK] Domain rewrite completed: $RECOVERY_OLD_DOMAIN -> $RECOVERY_NEW_DOM"
'''


class SSHDeployer:
    def __init__(self, host: str, port: int = 22, user: str = "root", password: str = "", key_data: str = "", cancel_check: Optional[Callable[[], bool]] = None):
        self.host = host
        self.port = str(port)
        self.user = user
        self.password = password
        self.key_data = key_data
        self.cancel_check = cancel_check
        self._key_file: Optional[str] = None
        self._askpass_file: Optional[str] = None

    async def __aenter__(self):
        if self.key_data.strip():
            tf = tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.key')
            tf.write(self.key_data.strip() + '\n')
            tf.close()
            os.chmod(tf.name, 0o600)
            self._key_file = tf.name
        if self.password and not self._key_file:
            py_exe = sys.executable
            if sys.platform == "win32":
                tf_pass = tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.bat')
                tf_pass.write(f'@"{py_exe}" -c "import os; print(os.environ.get(\'SSH_DEPLOY_PASSWORD\', \'\'))"\n')
                tf_pass.close()
                self._askpass_file = tf_pass.name
            else:
                tf_pass = tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.sh')
                tf_pass.write(f'#!/bin/sh\nexec "{py_exe}" -c "import os; print(os.environ.get(\'SSH_DEPLOY_PASSWORD\', \'\'))"\n')
                tf_pass.close()
                os.chmod(tf_pass.name, 0o700)
                self._askpass_file = tf_pass.name
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self._key_file and os.path.exists(self._key_file):
            try:
                os.remove(self._key_file)
            except Exception:
                pass
        if self._askpass_file and os.path.exists(self._askpass_file):
            try:
                os.remove(self._askpass_file)
            except Exception:
                pass

    def _build_ssh_cmd_and_env(self, remote_cmd: str) -> tuple[list[str], dict[str, str]]:
        cmd = [
            "ssh",
            "-o", "StrictHostKeyChecking=no",
            "-o", "UserKnownHostsFile=/dev/null",
            "-o", "LogLevel=ERROR",
            "-o", "ConnectTimeout=10",
            "-o", "NumberOfPasswordPrompts=1",
            "-p", self.port
        ]
        
        env = os.environ.copy()
        if self._key_file:
            cmd.extend(["-i", self._key_file])
        elif self._askpass_file:
            env["SSH_ASKPASS"] = self._askpass_file
            env["SSH_ASKPASS_REQUIRE"] = "force"
            env["DISPLAY"] = "dummy:0"
            if self.password:
                env["SSH_DEPLOY_PASSWORD"] = self.password
        target = f"{self.user}@{self.host}"
        cmd.extend([target, remote_cmd])
        return cmd, env

    async def exec_command(self, remote_cmd: str, log_callback: Optional[Callable[[str], None]] = None, stdin_data: Optional[bytes] = None) -> tuple[int, str]:
        cmd, env = self._build_ssh_cmd_and_env(remote_cmd)
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdin=asyncio.subprocess.PIPE if stdin_data else asyncio.subprocess.DEVNULL,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
                env=env
            )
            if stdin_data and proc.stdin:
                proc.stdin.write(stdin_data)
                await proc.stdin.drain()
                proc.stdin.close()

            output_lines = []
            in_json_block = False
            while True:
                if self.cancel_check and self.cancel_check():
                    try:
                        proc.terminate()
                        try:
                            proc.kill()
                            await proc.wait()
                        except Exception:
                            pass
                    except Exception:
                        pass
                    if log_callback:
                        log_callback("[CANCEL] Команда отменена пользователем.")
                    return 1, "Cancelled by user"
                try:
                    line = await asyncio.wait_for(proc.stdout.readline(), timeout=0.5)
                except asyncio.TimeoutError:
                    if proc.returncode is not None:
                        break
                    continue
                if not line:
                    break
                decoded = strip_ansi(line.decode('utf-8', errors='replace')).rstrip()
                if decoded:
                    output_lines.append(decoded)
                    
                    if "===RESULT_JSON_START===" in decoded:
                        in_json_block = True
                        
                    if log_callback and not in_json_block and "===RESULT_JSON_END===" not in decoded:
                        log_callback(decoded)
                        
                    if "===RESULT_JSON_END===" in decoded:
                        in_json_block = False
            await proc.wait()
            return proc.returncode or 0, "\n".join(output_lines)
        except Exception as e:
            err_msg = f"[ERROR] SSH execution error: {str(e)}"
            if log_callback:
                log_callback(err_msg)
            return 1, err_msg

    async def test_connection(self) -> tuple[bool, str]:
        rc, out = await self.exec_command("echo 'SSH_OK'")
        if rc == 0 and "SSH_OK" in out:
            return True, "Connection successful"
        return False, f"Connection error (Code {rc}): {out}"

    def _build_scp_cmd_and_env(self, remote_path: str, local_path: str) -> tuple[list[str], dict[str, str]]:
        cmd = [
            "scp",
            "-P", self.port,
            "-o", "StrictHostKeyChecking=no",
            "-o", "UserKnownHostsFile=/dev/null",
            "-o", "LogLevel=ERROR",
            "-o", "ConnectTimeout=10",
            "-o", "NumberOfPasswordPrompts=1",
        ]
        env = os.environ.copy()
        if self._key_file:
            cmd.extend(["-i", self._key_file])
        elif self._askpass_file:
            env["SSH_ASKPASS"] = self._askpass_file
            env["SSH_ASKPASS_REQUIRE"] = "force"
            env["DISPLAY"] = "dummy:0"
            if self.password:
                env["SSH_DEPLOY_PASSWORD"] = self.password
        target = f"{self.user}@{self.host}:{remote_path}"
        cmd.extend([target, local_path])
        return cmd, env

    async def download_file(self, remote_path: str, local_path: str, log_callback: Optional[Callable[[str], None]] = None) -> tuple[int, str]:
        cmd, env = self._build_scp_cmd_and_env(remote_path, local_path)
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdin=asyncio.subprocess.DEVNULL,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
                env=env
            )
            output_lines = []
            while True:
                if self.cancel_check and self.cancel_check():
                    try:
                        proc.terminate()
                        try:
                            proc.kill()
                            await proc.wait()
                        except Exception:
                            pass
                    except Exception:
                        pass
                    if log_callback:
                        log_callback("[CANCEL] Скачивание отменено пользователем.")
                    return 1, "Cancelled by user"
                try:
                    line = await asyncio.wait_for(proc.stdout.readline(), timeout=0.5)
                except asyncio.TimeoutError:
                    if proc.returncode is not None:
                        break
                    continue
                if not line:
                    break
                decoded = strip_ansi(line.decode('utf-8', errors='replace')).rstrip()
                if decoded:
                    output_lines.append(decoded)
                    if log_callback:
                        log_callback(decoded)
            await proc.wait()
            return proc.returncode or 0, "\n".join(output_lines)
        except Exception as e:
            err_msg = f"[ERROR] SCP download error: {str(e)}"
            if log_callback:
                log_callback(err_msg)
            return 1, err_msg



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


async def _deploy_node(host: str, port: int, user: str, password: str, key_data: str, env_vars: Dict[str, str], log: Callable[[str, str], None], cancel_check: Optional[Callable[[], bool]] = None, bundle_source_dir: Optional[str] = None, decoy_files: Optional[Dict[str, bytes]] = None) -> tuple[bool, str]:
    remote_dir = "/opt/3x-ui-bootstRUp"
    async with SSHDeployer(host, port, user, password, key_data, cancel_check=cancel_check) as deployer:
        log(f"Connecting to {host}:{port}...", "info")
        ok, msg = await deployer.test_connection()
        if not ok:
            log(f"SSH test failed for {host}: {msg}", "error")
            return False, ""

        log(f"Syncing local files to {host}...", "info")
        bundle_bytes = get_bundle_bytes(source_dir=bundle_source_dir, decoy_files=decoy_files)
        sync_cmd = f"mkdir -p {remote_dir} && tar -xzf - -C {remote_dir}"
        rc, sync_out = await deployer.exec_command(sync_cmd, lambda m: log(m, "info"), stdin_data=bundle_bytes)
        if rc != 0:
            log(f"[ERROR] Failed to transfer files to {host}: {sync_out}", "error")
            return False, ""

        log(f"Executing setup.sh script on {host}...", "info")
        
        env_str_parts = []
        for k, v in env_vars.items():
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

async def _deploy_sub_server(host: str, port: int, user: str, password: str, key_data: str, env_vars: Dict[str, str], log: Callable[[str, str], None], cancel_check: Optional[Callable[[], bool]] = None, bundle_source_dir: Optional[str] = None, decoy_files: Optional[Dict[str, bytes]] = None) -> tuple[bool, str]:
    remote_dir = "/opt/3x-ui-bootstRUp"
    async with SSHDeployer(host, port, user, password, key_data, cancel_check=cancel_check) as deployer:
        log(f"Connecting to Subscription Server on {host}:{port}...", "info")
        ok, msg = await deployer.test_connection()
        if not ok:
            log(f"SSH test failed for Subscription Server {host}: {msg}", "error")
            return False, ""

        log(f"Syncing local files to Subscription Server {host}...", "info")
        bundle_bytes = get_bundle_bytes(source_dir=bundle_source_dir, decoy_files=decoy_files)
        sync_cmd = _sub_server_sync_cmd(remote_dir, preserve=(env_vars.get("UPDATE_SUB_SERVER", "") == "1"))
        rc, sync_out = await deployer.exec_command(sync_cmd, lambda m: log(m, "info"), stdin_data=bundle_bytes)
        if rc != 0:
            log(f"[ERROR] Failed to transfer files to Subscription Server {host}: {sync_out}", "error")
            return False, ""

        log(f"Executing sub-server/setup.sh script on {host}...", "info")
        env_str_parts = []
        for k, v in env_vars.items():
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

    def _check_ssh(host_key: str, port_key: str, user_key: str, pass_key: str, key_key: str, label: str) -> Optional[str]:
        host = str(config.get(host_key, "") or "").strip()
        if not host:
            return f"Укажите домен {label}"
        port_val = config.get(port_key)
        try:
            p = int(port_val or 22)
            if p <= 0 or p > 65535:
                return f"Укажите корректный SSH порт {label} (1-65535)"
        except (ValueError, TypeError):
            return f"Укажите корректный SSH порт {label}"
        user = str(config.get(user_key, "") or "").strip()
        if not user:
            return f"Укажите SSH пользователя {label}"
        password = str(config.get(pass_key, "") or "")
        key_data = str(config.get(key_key, "") or "")
        if not password and not key_data:
            return f"Укажите SSH пароль или ключ {label}"
        return None

    if mode in ["single", "proxy_only", "freedom_only", "freedom_component", "freedom_sub"]:
        err = _check_ssh("vps_host", "vps_port", "vps_user", "vps_password", "vps_key", "VPS сервера")
        if err:
            return False, err
        if not str(config.get("xui_username", "") or "").strip():
            return False, "Укажите логин админа 3X-UI"
        if not str(config.get("xui_password", "") or "").strip():
            return False, "Укажите пароль админа 3X-UI"
        if not str(config.get("sub_secret", "") or "").strip():
            return False, "Укажите секретную фразу панели"
        if mode == "proxy_only":
            if not str(config.get("foreign_sub_url", "") or "").strip():
                return False, "Укажите ссылку подписки Freedom ноды (FOREIGN_SUB_URL)"
        elif mode in ["freedom_only", "freedom_sub"]:
            tcp = str(config.get("client_tcp_list", "") or "").strip()
            xhttp = str(config.get("client_xhttp_list", "") or "").strip()
            if not tcp and not xhttp:
                return False, "Укажите хотя бы одного клиента (VLESS TCP или VLESS XHTTP)"

        if mode == "freedom_sub":
            err = _check_ssh("sub_vps_host", "sub_vps_port", "sub_vps_user", "sub_vps_password", "sub_vps_key", "Сервера подписок")
            if err:
                return False, err
            if not str(config.get("sub_secret_path", "") or "").strip():
                return False, "Укажите префикс пути подписок Сервера подписок"
            if not str(config.get("sub_admin_user", "") or "").strip():
                return False, "Укажите логин админа Сервера подписок"
            if not str(config.get("sub_admin_password", "") or "").strip():
                return False, "Укажите пароль админа Сервера подписок"

    elif mode in ["cascade", "cascade_sub"]:
        err = _check_ssh("freedom_host", "freedom_port", "freedom_user", "freedom_password", "freedom_key", "Freedom Node")
        if err:
            return False, err
        if not str(config.get("freedom_xui_username", "") or "").strip():
            return False, "Укажите логин админа Freedom 3X-UI"
        if not str(config.get("freedom_xui_password", "") or "").strip():
            return False, "Укажите пароль админа Freedom 3X-UI"
        if not str(config.get("freedom_sub_secret", "") or "").strip():
            return False, "Укажите секретную фразу Freedom панели"

        err = _check_ssh("proxy_host", "proxy_port", "proxy_user", "proxy_password", "proxy_key", "Proxy Node")
        if err:
            return False, err
        if not str(config.get("proxy_xui_username", "") or "").strip():
            return False, "Укажите логин админа Proxy 3X-UI"
        if not str(config.get("proxy_xui_password", "") or "").strip():
            return False, "Укажите пароль админа Proxy 3X-UI"
        if not str(config.get("proxy_sub_secret", "") or "").strip():
            return False, "Укажите секретную фразу Proxy панели"

        if mode == "cascade_sub":
            err = _check_ssh("sub_vps_host", "sub_vps_port", "sub_vps_user", "sub_vps_password", "sub_vps_key", "Сервера подписок")
            if err:
                return False, err
            if not str(config.get("sub_secret_path", "") or "").strip():
                return False, "Укажите префикс пути подписок Сервера подписок"
            if not str(config.get("sub_admin_user", "") or "").strip():
                return False, "Укажите логин админа Сервера подписок"
            if not str(config.get("sub_admin_password", "") or "").strip():
                return False, "Укажите пароль админа Сервера подписок"

    elif mode == "sub_only":
        err = _check_ssh("sub_vps_host", "sub_vps_port", "sub_vps_user", "sub_vps_password", "sub_vps_key", "Сервера подписок")
        if err:
            return False, err
        if not str(config.get("sub_secret_path", "") or "").strip():
            return False, "Укажите префикс пути подписок Сервера подписок"
        if not str(config.get("sub_admin_user", "") or "").strip():
            return False, "Укажите логин админа Сервера подписок"
        if not str(config.get("sub_admin_password", "") or "").strip():
            return False, "Укажите пароль админа Сервера подписок"
        sub_rus = str(config.get("sub_russian_url", "") or "").strip()
        sub_for = str(config.get("sub_foreign_url", "") or "").strip()
        if not sub_rus and not sub_for:
            return False, "Укажите хотя бы одну ссылку подписки (RUSSIAN_SUB_URL или FOREIGN_SUB_URL)"

    elif mode == "backup":
        err = _check_ssh("backup_vps_host", "backup_vps_port", "backup_vps_user", "backup_vps_password", "backup_vps_key", "сервера для бэкапа")
        if err:
            return False, err

    elif mode == "recovery":
        err = _check_ssh("recovery_vps_host", "recovery_vps_port", "recovery_vps_user", "recovery_vps_password", "recovery_vps_key", "сервера для восстановления")
        if err:
            return False, err
        if not str(config.get("recovery_backup_file", "") or "").strip():
            return False, "Выберите архив бэкапа для восстановления"
        if not str(config.get("recovery_xui_username", "") or "").strip():
            return False, "Укажите логин админа 3X-UI из бэкапа"
        if not str(config.get("recovery_xui_password", "") or "").strip():
            return False, "Укажите пароль админа 3X-UI из бэкапа"

    elif mode in ["update", "update_3xui", "restart_panel", "restart_server"]:
        err = _check_ssh("update_vps_host", "update_vps_port", "update_vps_user", "update_vps_password", "update_vps_key", "сервера для обновления/перезапуска")
        if err:
            return False, err
        if mode in ["update", "update_3xui"]:
            ver = str(config.get("update_xui_version", "") or config.get("xui_version", "") or "").strip()
            if not ver:
                return False, "Укажите версию 3X-UI для обновления"

    elif mode in ["restart_sub", "update_sub", "backup_sub", "rollback_sub"]:
        err = _check_ssh("sub_vps_host", "sub_vps_port", "sub_vps_user", "sub_vps_password", "sub_vps_key", "Сервера подписок")
        if err:
            return False, err
        if mode == "rollback_sub" and not str(config.get("rollback_sub_backup_file", "") or "").strip():
            return False, "Выберите архив бэкапа Сервера подписок"

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

    # Remote Server Backup Mode
    if deploy_mode == "backup":
        from deployers.maintenance import deploy_backup
        return await deploy_backup(config, log, cancel_check)

    # Recovery Mode from Backup Archive
    if deploy_mode == "recovery":
        from deployers.maintenance import deploy_recovery
        return await deploy_recovery(config, log, cancel_check)

    # Remote Server 3X-UI Update Mode
    if deploy_mode in ["update", "update_3xui"]:
        from deployers.maintenance import deploy_update
        return await deploy_update(
            config, log, cancel_check,
            change_ssh_port=change_ssh_port,
            new_ssh_port=new_ssh_port,
            updated_ssh_ports=updated_ssh_ports,
            prepare_decoy_files=prepare_decoy_files,
        )

    # Maintenance Modes: Restart Panel / Server
    if deploy_mode in ["restart_panel", "restart_server"]:
        from deployers.maintenance import deploy_restart
        return await deploy_restart(config, log, cancel_check)

    # Subscription Server Maintenance Modes: Restart / Backup / Rollback
    if deploy_mode in ["restart_sub", "update_sub", "backup_sub", "rollback_sub"]:
        from deployers.maintenance import deploy_sub_ops
        return await deploy_sub_ops(
            config, log, cancel_check,
            change_ssh_port=change_ssh_port,
            new_ssh_port=new_ssh_port,
            updated_ssh_ports=updated_ssh_ports,
            prepare_decoy_files=prepare_decoy_files,
        )

    # Standalone Subscription Server Mode
    if deploy_mode == "sub_only":
        from deployers.sub_deployer import deploy_sub_only
        return await deploy_sub_only(
            config, log, cancel_check,
            bundle_dir=bundle_dir,
            change_ssh_port=change_ssh_port,
            new_ssh_port=new_ssh_port,
            updated_ssh_ports=updated_ssh_ports,
            prepare_decoy_files=prepare_decoy_files,
        )

    if deploy_mode in ["single", "proxy_only", "freedom_only", "freedom_component"]:
        from deployers.panel_deployer import deploy_single
        return await deploy_single(
            config, log, cancel_check,
            bundle_dir=bundle_dir,
            change_ssh_port=change_ssh_port,
            new_ssh_port=new_ssh_port,
            updated_ssh_ports=updated_ssh_ports,
            prepare_decoy_files=prepare_decoy_files,
        )

    if deploy_mode == "freedom_sub":
        from deployers.panel_deployer import deploy_freedom_sub
        return await deploy_freedom_sub(
            config, log, cancel_check,
            bundle_dir=bundle_dir,
            change_ssh_port=change_ssh_port,
            new_ssh_port=new_ssh_port,
            updated_ssh_ports=updated_ssh_ports,
            prepare_decoy_files=prepare_decoy_files,
        )

    if deploy_mode in ["cascade", "cascade_sub"]:
        from deployers.panel_deployer import deploy_cascade
        return await deploy_cascade(
            config, log, cancel_check,
            bundle_dir=bundle_dir,
            change_ssh_port=change_ssh_port,
            new_ssh_port=new_ssh_port,
            updated_ssh_ports=updated_ssh_ports,
            prepare_decoy_files=prepare_decoy_files,
        )
