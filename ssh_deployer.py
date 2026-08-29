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
from typing import Callable, Dict, Any, Optional, List, Tuple

ANSI_ESCAPE = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
REPO_ROOT = os.path.dirname(os.path.abspath(globals()["__file__"])) if globals().get("__file__") else os.path.abspath(os.path.dirname(sys.argv[0]) if sys.argv and sys.argv[0] else os.getcwd())

def strip_ansi(text: str) -> str:
    return ANSI_ESCAPE.sub('', text)

def get_bundle_bytes(source_dir: str | None = None) -> bytes:
    buf = io.BytesIO()
    repo_dir = source_dir or REPO_ROOT
    with tarfile.open(fileobj=buf, mode='w:gz') as tar:
        for root, dirs, files in os.walk(repo_dir):
            if '.git' in root or '.python_env' in root or '__pycache__' in root or (os.sep + 'panel' + os.sep + 'static') in root or 'backups_panel' in root or 'backups_sub_server' in root:
                continue
            for file in files:
                if file.endswith('.pyc') or file in ('setup_backup.yml', 'sub-server.log', 'servers.json', 'force-subs.yml', 'nodes.json', 'subs.yml'):
                    continue
                full_path = os.path.join(root, file)
                rel_path = os.path.relpath(full_path, repo_dir)
                tar.add(full_path, arcname=rel_path)
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
    return hashlib.md5(f"{secret}-sub".encode('utf-8')).hexdigest()[:16]


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


async def _deploy_node(host: str, port: int, user: str, password: str, key_data: str, env_vars: Dict[str, str], log: Callable[[str, str], None], cancel_check: Optional[Callable[[], bool]] = None, bundle_source_dir: Optional[str] = None) -> tuple[bool, str]:
    remote_dir = "/opt/3x-ui-bootstRUp"
    async with SSHDeployer(host, port, user, password, key_data, cancel_check=cancel_check) as deployer:
        log(f"Connecting to {host}:{port}...", "info")
        ok, msg = await deployer.test_connection()
        if not ok:
            log(f"SSH test failed for {host}: {msg}", "error")
            return False, ""

        log(f"Syncing local files to {host}...", "info")
        bundle_bytes = get_bundle_bytes(source_dir=bundle_source_dir)
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

async def _deploy_sub_server(host: str, port: int, user: str, password: str, key_data: str, env_vars: Dict[str, str], log: Callable[[str, str], None], cancel_check: Optional[Callable[[], bool]] = None, bundle_source_dir: Optional[str] = None) -> tuple[bool, str]:
    remote_dir = "/opt/3x-ui-bootstRUp"
    async with SSHDeployer(host, port, user, password, key_data, cancel_check=cancel_check) as deployer:
        log(f"Connecting to Subscription Server on {host}:{port}...", "info")
        ok, msg = await deployer.test_connection()
        if not ok:
            log(f"SSH test failed for Subscription Server {host}: {msg}", "error")
            return False, ""

        log(f"Syncing local files to Subscription Server {host}...", "info")
        bundle_bytes = get_bundle_bytes(source_dir=bundle_source_dir)
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

async def run_deployment(config: Dict[str, Any], log_callback: Callable[[str, str], None], cancel_check: Optional[Callable[[], bool]] = None) -> Tuple[bool, Dict[str, Any]]:
    bundle_dir = config.get("bundle_source_dir")
    def log(msg: str, level: str = "info"):
        log_callback(msg, level)

    deploy_mode = config.get("deploy_mode", "").strip()
    if not deploy_mode:
        deploy_mode = "cascade" if config.get("is_cascade", False) else "single"

    xui_username = config.get("xui_username", "").strip()
    xui_password = config.get("xui_password", "").strip()
    xui_version = config.get("xui_version", "").strip()
    sub_secret = config.get("sub_secret", "").strip()

    # Remote Server Backup Mode
    if deploy_mode == "backup":
        host = (config.get("backup_vps_host") or config.get("vps_host") or "").strip()
        port = int(config.get("backup_vps_port") or config.get("vps_port") or 22)
        user = (config.get("backup_vps_user") or config.get("vps_user") or "root").strip()
        password = config.get("backup_vps_password") if config.get("backup_vps_password") is not None else config.get("vps_password", "")
        key_data = config.get("backup_vps_key") if config.get("backup_vps_key") is not None else config.get("vps_key", "")

        if not host:
            log("[ERROR] Remote domain host is required for backup mode.", "error")
            return False, {}

        raw_backup_name = config.get("backup_name", "").strip()
        if not raw_backup_name:
            import datetime
            now_str = datetime.datetime.now().strftime("%Y-%m-%d_%H%M%S")
            raw_backup_name = f"{host}_{now_str}.tar.gz" if host else f"backup_{now_str}.tar.gz"
        elif not any(raw_backup_name.endswith(ext) for ext in [".tar.gz", ".tgz", ".zip", ".tar"]):
            raw_backup_name = f"{raw_backup_name}.tar.gz"

        backup_name = os.path.basename(raw_backup_name)

        log(f"Starting remote backup process for server {host}:{port}...", "info")
        async with SSHDeployer(host, port, user, password, key_data, cancel_check=cancel_check) as deployer:
            log(f"Connecting to {host}:{port}...", "info")
            ok, msg = await deployer.test_connection()
            if not ok:
                log(f"[ERROR] SSH connection failed: {msg}", "error")
                return False, {}

            bk_ok, bk_local_path, file_size_mb = await _perform_remote_backup(deployer, backup_name, log)
            if not bk_ok:
                return False, {}

            log("=========================================", "success")
            log("🎉 BACKUP CREATED AND DOWNLOADED SUCCESSFULLY!", "success")
            log(f"Local backup location: ./backups_panel/{backup_name} ({file_size_mb} MB)", "success")
            log("=========================================", "success")

            return True, {
                "deploy_mode": "backup",
                "backup_host": host,
                "backup_name": backup_name,
                "backup_path": f"./backups_panel/{backup_name}",
                "file_size": f"{file_size_mb} MB"
            }

    # Recovery Mode from Backup Archive
    if deploy_mode == "recovery":
        host = (config.get("recovery_vps_host") or config.get("vps_host") or "").strip()
        port = int(config.get("recovery_vps_port") or config.get("vps_port") or 22)
        user = (config.get("recovery_vps_user") or config.get("vps_user") or "root").strip()
        password = config.get("recovery_vps_password") if config.get("recovery_vps_password") is not None else config.get("vps_password", "")
        key_data = config.get("recovery_vps_key") if config.get("recovery_vps_key") is not None else config.get("vps_key", "")
        backup_filename = config.get("recovery_backup_file", "").strip()
        recovery_panel_user = config.get("recovery_xui_username", "").strip() or "admin"
        recovery_panel_pass = config.get("recovery_xui_password", "").strip() or "admin"
        recovery_creds_provided = bool(config.get("recovery_xui_username") or config.get("recovery_xui_password"))

        if not host:
            log("[ERROR] Target domain host is required for recovery mode.", "error")
            return False, {}

        if not backup_filename:
            log("[ERROR] Backup file must be selected for recovery mode.", "error")
            return False, {}

        repo_root = REPO_ROOT
        local_backup_path = os.path.join(repo_root, "backups_panel", os.path.basename(backup_filename))

        if not os.path.isfile(local_backup_path):
            log(f"[ERROR] Selected backup archive '{backup_filename}' not found in ./backups_panel/", "error")
            return False, {}

        # Inspect the backup archive locally: old domain + hidden web base path
        old_domain = ""
        web_base_path = ""
        try:
            with tarfile.open(local_backup_path, "r:*") as tar:
                for member in tar.getmembers():
                    if member.name.endswith("Caddyfile"):
                        ef = tar.extractfile(member)
                        if ef:
                            caddy_text = ef.read().decode("utf-8", errors="replace")
                            m_dom = re.search(r'email 3xui@([A-Za-z0-9.-]+)', caddy_text)
                            if not m_dom:
                                m_dom = re.search(r'^([A-Za-z0-9.-]+):[0-9]+', caddy_text, re.MULTILINE)
                            if m_dom:
                                old_domain = m_dom.group(1).strip()
                            m_path = re.search(r'@web_base_path\s+path\s+/([A-Za-z0-9_-]+)', caddy_text)
                            if m_path:
                                web_base_path = m_path.group(1)
                        break
        except Exception:
            pass

        domain_changed = bool(old_domain) and old_domain.lower() != host.lower()
        if domain_changed and not recovery_creds_provided:
            log(f"[ERROR] Domain change detected in the backup (old: '{old_domain}' -> new: '{host}'). "
                f"Rewriting the domain inside the 3x-UI panel is done via its HTTP API and requires the "
                f"panel admin credentials. Fill in the 3X-UI login/password fields in the recovery form "
                f"(default for a fresh deployment is admin/admin).", "error")
            return False, {}

        with open(local_backup_path, "rb") as f:
            backup_bytes = f.read()

        remote_dir = "/opt/3x-ui-bootstRUp"

        log(f"Starting Recovery process for server {host}:{port} using '{backup_filename}'...", "info")
        async with SSHDeployer(host, port, user, password, key_data, cancel_check=cancel_check) as deployer:
            log(f"Connecting to {host}:{port}...", "info")
            ok, msg = await deployer.test_connection()
            if not ok:
                log(f"[ERROR] SSH connection failed: {msg}", "error")
                return False, {}

            log(f"Syncing local tool files to {host}...", "info")
            bundle_bytes = get_bundle_bytes()
            sync_cmd = f"mkdir -p {remote_dir} && tar -xzf - -C {remote_dir}"
            rc, sync_out = await deployer.exec_command(sync_cmd, lambda m: log(m, "info"), stdin_data=bundle_bytes)
            if rc != 0:
                log(f"[ERROR] Failed to transfer tool files to {host}: {sync_out}", "error")
                return False, {}

            log(f"Uploading backup archive ({len(backup_bytes)} bytes) to {host}...", "info")
            upload_cmd = "cat > /tmp/recovery_backup.tar.gz"
            rc, up_out = await deployer.exec_command(upload_cmd, lambda m: log(m, "info"), stdin_data=backup_bytes)
            if rc != 0:
                log(f"[ERROR] Failed to upload backup archive to {host}: {up_out}", "error")
                return False, {}

            log("Extracting backup and launching Docker Compose...", "info")
            
            new_domain_str = shlex.quote(host)
            remote_script = (
                "set -e\n"
                "cd /opt/3x-ui-bootstRUp\n"
                "COMPOSE_FILE=\"working/docker-compose/docker-compose.yml\"\n"
                "if [ -f \"$COMPOSE_FILE\" ]; then\n"
                "  docker compose -f \"$COMPOSE_FILE\" --project-directory . down --remove-orphans 2>/dev/null || true\n"
                "fi\n"
                "docker stop 3xui caddy nginx-decoy 2>/dev/null || true\n"
                "docker rm 3xui caddy nginx-decoy 2>/dev/null || true\n"
                "rm -rf ./working && mkdir -p ./working\n"
                "tar -xzf /tmp/recovery_backup.tar.gz -C ./working\n"
                "rm -f /tmp/recovery_backup.tar.gz\n"
                "\n"
                "# Domain replacement if domain changed\n"
                "CADDY_FILE=\"working/caddy/Caddyfile\"\n"
                "NEW_DOM=" + new_domain_str + "\n"
                "if [ -f \"$CADDY_FILE\" ]; then\n"
                "  OLD_DOMAIN=$(grep -oE 'email 3xui@[A-Za-z0-9.-]+' \"$CADDY_FILE\" | head -n 1 | cut -d'@' -f2 || true)\n"
                "  if [ -z \"$OLD_DOMAIN\" ]; then\n"
                "    OLD_DOMAIN=$(grep -oE '^[A-Za-z0-9.-]+:[0-9]+' \"$CADDY_FILE\" | head -n 1 | cut -d':' -f1 || true)\n"
                "  fi\n"
                "  if [ -n \"$OLD_DOMAIN\" ] && [ \"$OLD_DOMAIN\" != \"$NEW_DOM\" ]; then\n"
                "    echo \"[INFO] Domain change detected from '$OLD_DOMAIN' to '$NEW_DOM'. Updating Caddyfile & configs...\"\n"
                "    ESC_OLD=$(printf '%s\\n' \"$OLD_DOMAIN\" | sed -e 's/[\\/&]/\\\\&/g')\n"
                "    ESC_NEW=$(printf '%s\\n' \"$NEW_DOM\" | sed -e 's/[\\/&]/\\\\&/g')\n"
                "    sed -i \"s/$ESC_OLD/$ESC_NEW/g\" \"$CADDY_FILE\"\n"
                "    [ -f \"working/nginx-decoy/default.conf\" ] && sed -i \"s/$ESC_OLD/$ESC_NEW/g\" \"working/nginx-decoy/default.conf\" || true\n"
                "    rm -rf working/.caddy_data 2>/dev/null || true\n"
                "    docker volume rm caddy_data 2>/dev/null || true\n"
                "  fi\n"
                "  WEB_PATH=$(grep -oE '@web_base_path path /[^ /]+' \"$CADDY_FILE\" | head -n 1 | awk '{print $3}' | tr -d '/' || true)\n"
                "  if [ -n \"$WEB_PATH\" ]; then\n"
                "    echo \"RECOVERY_WEB_PATH=$WEB_PATH\"\n"
                "  fi\n"
                "fi\n"
                "\n"
                + LEGACY_COMPOSE_REWRITE_CMD +
                "\n"
                "if [ -f \"$COMPOSE_FILE\" ]; then\n"
                "  docker compose -f \"$COMPOSE_FILE\" --project-directory . up -d\n"
                "else\n"
                "  echo \"[ERROR] docker-compose.yml not found in backup!\"\n"
                "  exit 1\n"
                "fi\n"
            )

            rc, out = await deployer.exec_command(f"bash -c {shlex.quote(remote_script)}", lambda m: log(m, "info"))
            if rc != 0:
                log(f"[ERROR] Recovery extraction or container startup failed: {out}", "error")
                return False, {}

            m_path_out = re.search(r'RECOVERY_WEB_PATH=([A-Za-z0-9_-]+)', out)
            if m_path_out:
                web_base_path = m_path_out.group(1)

            if not web_base_path:
                try:
                    with tarfile.open(local_backup_path, "r:*") as tar:
                        for member in tar.getmembers():
                            if member.name.endswith("Caddyfile"):
                                ef = tar.extractfile(member)
                                if ef:
                                    caddy_text = ef.read().decode("utf-8", errors="replace")
                                    m_path = re.search(r'@web_base_path\s+path\s+/([A-Za-z0-9_-]+)', caddy_text)
                                    if m_path:
                                        web_base_path = m_path.group(1)
                                        break
                except Exception:
                    pass

            # Rewrite the domain inside the running 3x-UI panel via its HTTP API
            # (serverName / client `add` / externalProxy dest / subURI), so the
            # regenerated subscriptions point to the new host. No SQLite access.
            if domain_changed:
                log(f"Rewriting panel domain '{old_domain}' -> '{host}' via the 3x-UI HTTP API...", "info")
                rc_scr, scr_out = await deployer.exec_command(
                    "cat > /tmp/panel_domain_rewrite.sh",
                    lambda m: log(m, "info"),
                    stdin_data=PANEL_DOMAIN_REWRITE_SCRIPT.encode("utf-8"),
                )
                if rc_scr != 0:
                    log(f"[ERROR] Failed to upload the domain-rewrite script: {scr_out}", "error")
                    return False, {}
                rewrite_env = (
                    f"RECOVERY_OLD_DOMAIN={shlex.quote(old_domain)} "
                    f"RECOVERY_NEW_DOM={shlex.quote(host)} "
                    f"RECOVERY_PANEL_USER={shlex.quote(recovery_panel_user)} "
                    f"RECOVERY_PANEL_PASS={shlex.quote(recovery_panel_pass)}"
                )
                rc_rewrite, out_rewrite = await deployer.exec_command(
                    f"{rewrite_env} bash /tmp/panel_domain_rewrite.sh",
                    lambda m: log(m, "info"),
                )
                if rc_rewrite != 0:
                    log(f"[ERROR] Panel domain rewrite failed: {out_rewrite}", "error")
                    return False, {}
                log("✅ Panel domain rewritten (serverName / client add / subURI).", "success")

            xui_url = f"https://{host}/{web_base_path}/" if web_base_path else f"https://{host}/"

            log("=========================================", "success")
            log("🎉 RECOVERY COMPLETED SUCCESSFULLY!", "success")
            log(f"Server {host} restored from backup '{backup_filename}'", "success")
            log(f"Panel URL: {xui_url}", "success")
            log("=========================================", "success")

            return True, {
                "deploy_mode": "recovery",
                "recovery_host": host,
                "backup_file": backup_filename,
                "xui_url": xui_url
            }

    # Remote Server 3X-UI Update Mode
    if deploy_mode in ["update", "update_3xui"]:
        host = (config.get("update_vps_host") or config.get("vps_host") or "").strip()
        port = int(config.get("update_vps_port") or config.get("vps_port") or 22)
        user = (config.get("update_vps_user") or config.get("vps_user") or "root").strip()
        password = config.get("update_vps_password") if config.get("update_vps_password") is not None else config.get("vps_password", "")
        key_data = config.get("update_vps_key") if config.get("update_vps_key") is not None else config.get("vps_key", "")
        target_version = (config.get("update_xui_version") or config.get("xui_version")).strip()

        if not host:
            log("[ERROR] Remote host is required for update mode.", "error")
            return False, {}

        remote_dir = "/opt/3x-ui-bootstRUp"

        log(f"Starting 3X-UI update process for server {host}:{port} to version '{target_version}'...", "info")
        async with SSHDeployer(host, port, user, password, key_data, cancel_check=cancel_check) as deployer:
            log(f"Connecting to {host}:{port}...", "info")
            ok, msg = await deployer.test_connection()
            if not ok:
                log(f"[ERROR] SSH connection failed: {msg}", "error")
                return False, {}

            log(f"Syncing local tool scripts to {host}:{remote_dir}...", "info")
            bundle_bytes = get_bundle_bytes()
            sync_cmd = f"mkdir -p {remote_dir} && tar -xzf - -C {remote_dir}"
            rc, sync_out = await deployer.exec_command(sync_cmd, lambda m: log(m, "info"), stdin_data=bundle_bytes)
            if rc != 0:
                log(f"[ERROR] Failed to transfer scripts to {host}: {sync_out}", "error")
                return False, {}

            # --- Pre-update backup: create on server and download locally ---
            log("📦 Creating pre-update backup before version change...", "info")
            import datetime as _dt
            now_str = _dt.datetime.now().strftime("%Y-%m-%d_%H%M%S")
            backup_name = f"{host}_pre-update_{now_str}.tar.gz"

            bk_ok, bk_local_path, file_size_mb = await _perform_remote_backup(deployer, backup_name, log)
            if not bk_ok:
                return False, {}

            log(f"✅ Pre-update backup saved: ./backups_panel/{backup_name} ({file_size_mb} MB)", "success")
            # --- End of pre-update backup ---

            log(f"Executing remote panel_update.sh {target_version}...", "info")
            version_str = shlex.quote(target_version)
            remote_script = (
                "set -e\n"
                "WORK_DIR=\"/opt/3x-ui-bootstRUp\"\n"
                "if [ ! -d \"$WORK_DIR\" ]; then\n"
                "  if [ -d \"./working\" ]; then WORK_DIR=\".\"; else WORK_DIR=\"$(pwd)\"; fi\n"
                "fi\n"
                "cd \"$WORK_DIR\"\n"
                "chmod +x panel_update.sh panel_backup.sh 2>/dev/null || true\n"
                "bash panel_update.sh " + version_str + "\n"
            )

            rc, out = await deployer.exec_command(f"bash -c {shlex.quote(remote_script)}", lambda m: log(m, "info"))
            if rc != 0:
                log(f"[ERROR] Remote 3X-UI update failed: {out}", "error")
                return False, {}

            web_base_path = ""
            caddy_cmd = "cat /opt/3x-ui-bootstRUp/working/caddy/Caddyfile 2>/dev/null || cat working/caddy/Caddyfile 2>/dev/null || true"
            rc_cad, cad_out = await deployer.exec_command(caddy_cmd)
            if rc_cad == 0 and cad_out:
                m_path = re.search(r'@web_base_path\s+path\s+/([A-Za-z0-9_-]+)', cad_out)
                if m_path:
                    web_base_path = m_path.group(1)

            xui_url = f"https://{host}/{web_base_path}/" if web_base_path else f"https://{host}/"

            log("=========================================", "success")
            log("🎉 3X-UI PANEL UPDATED SUCCESSFULLY!", "success")
            log(f"Server: {host}:{port}", "success")
            log(f"New 3x-ui version: {target_version}", "success")
            log(f"Panel URL: {xui_url}", "success")
            log(f"Pre-update backup: ./backups_panel/{backup_name} ({file_size_mb} MB)", "success")
            log("=========================================", "success")

            return True, {
                "deploy_mode": "update_3xui",
                "update_host": host,
                "xui_version": target_version,
                "xui_url": xui_url,
                "backup_name": backup_name,
                "backup_path": f"./backups_panel/{backup_name}",
                "backup_size": f"{file_size_mb} MB"
            }

    # Maintenance Modes: Restart Panel / Server
    if deploy_mode in ["restart_panel", "restart_server"]:
        host = (config.get("update_vps_host") or config.get("vps_host") or "").strip()
        port = int(config.get("update_vps_port") or config.get("vps_port") or 22)
        user = (config.get("update_vps_user") or config.get("vps_user") or "root").strip()
        password = config.get("update_vps_password") if config.get("update_vps_password") is not None else config.get("vps_password", "")
        key_data = config.get("update_vps_key") if config.get("update_vps_key") is not None else config.get("vps_key", "")

        if not host:
            log(f"[ERROR] Remote host is required for {deploy_mode}.", "error")
            return False, {}

        log(f"Starting {deploy_mode} process for server {host}:{port}...", "info")
        async with SSHDeployer(host, port, user, password, key_data, cancel_check=cancel_check) as deployer:
            log(f"Connecting to {host}:{port}...", "info")
            ok, msg = await deployer.test_connection()
            if not ok:
                log(f"[ERROR] SSH connection failed: {msg}", "error")
                return False, {}

            if deploy_mode == "restart_panel":
                log("Restarting 3x-ui panel via docker compose...", "info")
                remote_script = (
                    "set -e\n"
                    "WORK_DIR=\"/opt/3x-ui-bootstRUp\"\n"
                    "if [ ! -d \"$WORK_DIR\" ]; then\n"
                    "  if [ -d \"./working\" ]; then WORK_DIR=\".\"; else WORK_DIR=\"$(pwd)\"; fi\n"
                    "fi\n"
                    "cd \"$WORK_DIR\"\n"
                    "COMPOSE_FILE=\"working/docker-compose/docker-compose.yml\"\n"
                    "if [ -f \"$COMPOSE_FILE\" ]; then\n"
                    "  docker compose -f \"$COMPOSE_FILE\" --project-directory . down --remove-orphans 2>/dev/null || true\n"
                    "fi\n"
                    "docker stop 3xui caddy nginx-decoy 2>/dev/null || true\n"
                    "docker rm 3xui caddy nginx-decoy 2>/dev/null || true\n"
                    + LEGACY_TEMPLATES_SYMLINK_CMD +
                    "docker compose -f \"$COMPOSE_FILE\" --project-directory . up -d\n"
                )
                rc, out = await deployer.exec_command(f"bash -c {shlex.quote(remote_script)}", lambda m: log(m, "info"))
                if rc != 0:
                    log(f"[ERROR] Panel restart failed: {out}", "error")
                    return False, {}
                
                log("✅ Panel restarted successfully!", "success")
                return True, {"deploy_mode": deploy_mode, "host": host}
            
            elif deploy_mode == "restart_server":
                log("Restarting server...", "info")
                rc, out = await deployer.exec_command("sudo reboot || reboot")
                log("✅ Reboot command sent!", "success")
                return True, {"deploy_mode": deploy_mode, "host": host}

    # Subscription Server Maintenance Modes: Restart / Backup / Rollback
    if deploy_mode in ["restart_sub", "update_sub", "backup_sub", "rollback_sub"]:
        sub_host = (config.get("sub_vps_host") or config.get("vps_host") or "").strip()
        sub_port = int(config.get("sub_vps_port") or config.get("vps_port") or 22)
        sub_user = (config.get("sub_vps_user") or config.get("vps_user") or "root").strip()
        sub_password = config.get("sub_vps_password") if config.get("sub_vps_password") is not None else config.get("vps_password", "")
        sub_key = config.get("sub_vps_key") if config.get("sub_vps_key") is not None else config.get("vps_key", "")

        if not sub_host:
            log(f"[ERROR] Subscription Server host is required for {deploy_mode}.", "error")
            return False, {}

        log(f"Starting {deploy_mode} process for Subscription Server {sub_host}:{sub_port}...", "info")
        async with SSHDeployer(sub_host, sub_port, sub_user, sub_password, sub_key, cancel_check=cancel_check) as deployer:
            log(f"Connecting to {sub_host}:{sub_port}...", "info")
            ok, msg = await deployer.test_connection()
            if not ok:
                log(f"[ERROR] SSH connection failed: {msg}", "error")
                return False, {}

            if deploy_mode == "restart_sub":
                log(f"Syncing local tool files to Subscription Server {sub_host}...", "info")
                bundle_bytes = get_bundle_bytes()
                sync_cmd = _sub_server_sync_cmd("/opt/3x-ui-bootstRUp", preserve=True)
                rc, sync_out = await deployer.exec_command(sync_cmd, lambda m: log(m, "info"), stdin_data=bundle_bytes)
                if rc != 0:
                    log(f"[ERROR] Failed to transfer tool files to {sub_host}: {sync_out}", "error")
                    return False, {}

                log("Restarting sub-server containers via sub-server/restart.sh...", "info")
                remote_script = (
                    "set -e\n"
                    "WORK_DIR=\"/opt/3x-ui-bootstRUp\"\n"
                    "if [ ! -d \"$WORK_DIR\" ]; then\n"
                    "  if [ -d \"./working\" ]; then WORK_DIR=\".\"; else WORK_DIR=\"$(pwd)\"; fi\n"
                    "fi\n"
                    "cd \"$WORK_DIR\"\n"
                    "bash sub-server/restart.sh\n"
                )
                rc, out = await deployer.exec_command(f"bash -c {shlex.quote(remote_script)}", lambda m: log(m, "info"))
                if rc != 0:
                    log(f"[ERROR] Sub-server restart failed: {out}", "error")
                    return False, {}

                log("✅ Subscription Server restarted successfully!", "success")
                return True, {"deploy_mode": deploy_mode, "sub_host": sub_host}

            if deploy_mode == "update_sub":
                import datetime
                now_str = datetime.datetime.now().strftime("%Y-%m-%d_%H%M%S")
                pre_backup_name = f"{sub_host}_pre-update_{now_str}.tar.gz"
                log("📦 Creating full pre-update backup before changing Subscription Server files...", "info")
                bk_ok, bk_local_path, file_size_mb = await _perform_remote_backup(
                    deployer, pre_backup_name, log, target="sub_server"
                )
                if not bk_ok:
                    log("[ERROR] Update aborted because the pre-update backup could not be created.", "error")
                    return False, {}
                log(
                    f"✅ Pre-update backup saved: ./backups_sub_server/{pre_backup_name} ({file_size_mb} MB)",
                    "success",
                )

                sub_env = {
                    "UPDATE_SUB_SERVER": "1",
                    # setup.sh reads DOMAIN/path/URLs/admin credentials from the
                    # existing generated compose/Caddy config in update mode.
                }
                log("Updating Subscription Server files and containers; client data will be preserved...", "info")
                ok_sub, out_sub = await _deploy_sub_server(
                    sub_host, sub_port, sub_user, sub_password, sub_key, sub_env, log,
                    cancel_check=cancel_check
                )
                if not ok_sub:
                    log(f"[ERROR] Subscription Server update failed: {out_sub}", "error")
                    return False, {}
                log("✅ Subscription Server updated successfully; clients and nodes preserved!", "success")
                return True, {
                    "deploy_mode": deploy_mode,
                    "sub_host": sub_host,
                    "pre_update_backup": f"./backups_sub_server/{pre_backup_name}",
                }

            if deploy_mode == "backup_sub":
                raw_backup_name = config.get("backup_name", "").strip()
                if not raw_backup_name:
                    import datetime
                    now_str = datetime.datetime.now().strftime("%Y-%m-%d_%H%M%S")
                    raw_backup_name = f"{sub_host}_sub_{now_str}.tar.gz"
                elif not any(raw_backup_name.endswith(ext) for ext in [".tar.gz", ".tgz", ".zip", ".tar"]):
                    raw_backup_name = f"{raw_backup_name}.tar.gz"
                backup_name = os.path.basename(raw_backup_name)

                bk_ok, bk_local_path, file_size_mb = await _perform_remote_backup(deployer, backup_name, log, target="sub_server")
                if not bk_ok:
                    return False, {}

                log("=========================================", "success")
                log("🎉 SUB-SERVER BACKUP CREATED AND DOWNLOADED SUCCESSFULLY!", "success")
                log(f"Local backup location: ./backups_sub_server/{backup_name} ({file_size_mb} MB)", "success")
                log("=========================================", "success")

                return True, {
                    "deploy_mode": "backup_sub",
                    "sub_host": sub_host,
                    "backup_name": backup_name,
                    "backup_path": f"./backups_sub_server/{backup_name}",
                    "file_size": f"{file_size_mb} MB"
                }

            if deploy_mode == "rollback_sub":
                backup_filename = config.get("rollback_sub_backup_file", "").strip()
                if not backup_filename:
                    log("[ERROR] Backup file must be selected for rollback_sub mode.", "error")
                    return False, {}

                repo_root = REPO_ROOT
                local_backup_path = os.path.join(repo_root, "backups_sub_server", os.path.basename(backup_filename))

                if not os.path.isfile(local_backup_path):
                    log(f"[ERROR] Selected backup archive '{backup_filename}' not found in ./backups_sub_server/", "error")
                    return False, {}

                with open(local_backup_path, "rb") as f:
                    backup_bytes = f.read()

                log(f"Uploading sub-server backup archive ({len(backup_bytes)} bytes) to {sub_host}...", "info")
                upload_cmd = "cat > /tmp/sub_rollback_backup.tar.gz"
                rc, up_out = await deployer.exec_command(upload_cmd, lambda m: log(m, "info"), stdin_data=backup_bytes)
                if rc != 0:
                    log(f"[ERROR] Failed to upload backup archive to {sub_host}: {up_out}", "error")
                    return False, {}

                log("Restoring configs and restarting Subscription Server containers...", "info")
                remote_script = (
                    "set -e\n"
                    "WORK_DIR=\"/opt/3x-ui-bootstRUp\"\n"
                    "if [ ! -d \"$WORK_DIR\" ]; then\n"
                    "  if [ -d \"./working\" ]; then WORK_DIR=\".\"; else WORK_DIR=\"$(pwd)\"; fi\n"
                    "fi\n"
                    "cd \"$WORK_DIR\"\n"
                    "COMPOSE_FILE=\"working/docker-compose/docker-compose.yml\"\n"
                    "if [ -f \"$COMPOSE_FILE\" ]; then\n"
                    "  docker compose -f \"$COMPOSE_FILE\" --project-directory . down --remove-orphans 2>/dev/null || true\n"
                    "fi\n"
                    "docker stop subs-server sub-caddy 2>/dev/null || true\n"
                    "docker rm subs-server sub-caddy 2>/dev/null || true\n"
                    "rm -rf /tmp/sub_restore && mkdir -p /tmp/sub_restore\n"
                    "tar -xzf /tmp/sub_rollback_backup.tar.gz -C /tmp/sub_restore\n"
                    "rm -f /tmp/sub_rollback_backup.tar.gz\n"
                    "mkdir -p sub-server working/caddy working/docker-compose\n"
                    "[ -f /tmp/sub_restore/subs.yml ] && cp /tmp/sub_restore/subs.yml sub-server/subs.yml || true\n"
                    "[ -f /tmp/sub_restore/force-subs.yml ] && cp /tmp/sub_restore/force-subs.yml sub-server/force-subs.yml || true\n"
                    "[ -f /tmp/sub_restore/nodes.json ] && cp /tmp/sub_restore/nodes.json sub-server/nodes.json || true\n"
                    "[ -f /tmp/sub_restore/working/Caddyfile ] && cp /tmp/sub_restore/working/Caddyfile working/caddy/Caddyfile || true\n"
                    "[ -f /tmp/sub_restore/working/docker-compose.yml ] && cp /tmp/sub_restore/working/docker-compose.yml working/docker-compose/docker-compose.yml || true\n"
                    "if [ -d /tmp/sub_restore/.caddy_data ]; then\n"
                    "  rm -rf .caddy_data && cp -r /tmp/sub_restore/.caddy_data .caddy_data\n"
                    "fi\n"
                    "rm -rf /tmp/sub_restore\n"
                    "if [ -f \"$COMPOSE_FILE\" ]; then\n"
                    "  docker compose -f \"$COMPOSE_FILE\" --project-directory . up -d\n"
                    "else\n"
                    "  echo \"[ERROR] docker-compose.yml not found after restore!\"\n"
                    "  exit 1\n"
                    "fi\n"
                    "SECRET_SUB_PATH=$(grep -oE 'handle /[A-Za-z0-9_-]+' working/caddy/Caddyfile 2>/dev/null | head -n 1 | sed 's|handle /||' || true)\n"
                    "if [ -n \"$SECRET_SUB_PATH\" ]; then\n"
                    "  echo \"SUB_SECRET_PATH=$SECRET_SUB_PATH\"\n"
                    "fi\n"
                )
                rc, out = await deployer.exec_command(f"bash -c {shlex.quote(remote_script)}", lambda m: log(m, "info"))
                if rc != 0:
                    log(f"[ERROR] Sub-server rollback failed: {out}", "error")
                    return False, {}

                sub_secret_path = ""
                m_sub_out = re.search(r'SUB_SECRET_PATH=([A-Za-z0-9_-]+)', out)
                if m_sub_out:
                    sub_secret_path = m_sub_out.group(1)

                log("=========================================", "success")
                log("🎉 SUB-SERVER ROLLBACK COMPLETED SUCCESSFULLY!", "success")
                log(f"Subscription Server {sub_host} restored from '{backup_filename}'", "success")
                if sub_secret_path:
                    log(f"Subscriptions base URL: https://{sub_host}/{sub_secret_path}", "success")
                log("=========================================", "success")

                result = {
                    "deploy_mode": "rollback_sub",
                    "sub_host": sub_host,
                    "backup_file": backup_filename
                }
                if sub_secret_path:
                    result["sub_base_url"] = f"https://{sub_host}/{sub_secret_path}"
                return True, result

    # Standalone Subscription Server Mode
    if deploy_mode == "sub_only":
        sub_host = config.get("sub_vps_host", "").strip() or config.get("vps_host", "").strip()
        sub_port = int(config.get("sub_vps_port") or config.get("vps_port") or 22)
        sub_user = config.get("sub_vps_user", "").strip() or config.get("vps_user", "root").strip()
        sub_password = config.get("sub_vps_password", config.get("vps_password", ""))
        sub_key = config.get("sub_vps_key", config.get("vps_key", ""))
        sub_domain = config.get("sub_domain", "").strip() or sub_host
        sub_secret_path = config.get("sub_secret_path", "").strip()
        sub_secret_path = sub_secret_path.strip("/")

        sub_russian_url = config.get("sub_russian_url", "").strip()
        sub_foreign_url = config.get("sub_foreign_url", "").strip()

        proxy_raw = config.get("sub_proxy_clients", "").strip()
        freedom_raw = config.get("sub_freedom_clients", "").strip()
        proxy_clients = [n.strip() for n in re.split(r'[\s,]+', proxy_raw) if n.strip()]
        freedom_clients = [n.strip() for n in re.split(r'[\s,]+', freedom_raw) if n.strip()]

        log(f"Starting deployment of Subscription Server on {sub_host}...", "info")
        sub_admin_user = config.get("sub_admin_user", "").strip()
        sub_admin_password = config.get("sub_admin_password", "").strip()
        sub_proxy_url, sub_foreign_url, _ = resolve_sub_server_urls(sub_russian_url, sub_foreign_url)
        sub_env = {
            "DOMAIN": sub_domain,
            "SECRET_SUB_PATH": sub_secret_path,
            "RUSSIAN_SUB_URL": sub_proxy_url,
            "FOREIGN_SUB_URL": sub_foreign_url,
            "PROXY_CLIENTS": " ".join(proxy_clients),
            "FREEDOM_CLIENTS": " ".join(freedom_clients),
            "ADMIN_USER": sub_admin_user,
            "ADMIN_PASSWORD": sub_admin_password
        }

        ok_sub, out_sub = await _deploy_sub_server(sub_host, sub_port, sub_user, sub_password, sub_key, sub_env, log, cancel_check=cancel_check, bundle_source_dir=bundle_dir)
        if not ok_sub:
            log("[ERROR] Failed to deploy Subscription Server.", "error")
            return False, {}

        base_sub_url = f"https://{sub_domain}/{sub_secret_path}"
        sub_clients = []
        for c in proxy_clients:
            sub_clients.append({
                "name": c,
                "sub_url": f"{base_sub_url}/{c}",
                "group": "Proxy (Russian Node)"
            })
        for c in freedom_clients:
            sub_clients.append({
                "name": c,
                "sub_url": f"{base_sub_url}/{c}",
                "group": "Freedom (Foreign Node)"
            })

        log("=========================================", "success")
        log("🎉 SUBSCRIPTION SERVER DEPLOYED SUCCESSFULLY!", "success")
        log(f"Subscription URL Base: {base_sub_url}/<username>", "success")
        log(f"Panel: {base_sub_url}  (admin: {sub_admin_user} / password: ••••••••)", "success")
        log("=========================================", "success")

        result_data = {
            "deploy_mode": "sub_only",
            "sub_domain": sub_domain,
            "sub_secret_path": sub_secret_path,
            "sub_base_url": base_sub_url,
            "sub_admin_user": sub_admin_user,
            "sub_admin_password": sub_admin_password,
            "clients": sub_clients
        }
        return True, result_data

    tcp_raw = config.get("client_tcp_list", "").strip()
    xhttp_raw = config.get("client_xhttp_list", "").strip()
    clients_tcp_str = " ".join([name.strip() for name in re.split(r'[\s,]+', tcp_raw) if name.strip()])
    clients_xhttp_str = " ".join([name.strip() for name in re.split(r'[\s,]+', xhttp_raw) if name.strip()])

    web_base_path = hashlib.md5(f"{sub_secret}-panel".encode('utf-8')).hexdigest()[:16]
    log("Generated secure deployment configuration.", "info")

    if deploy_mode in ["single", "proxy_only", "freedom_only", "freedom_component"]:
        host = config.get("vps_host", "").strip()
        port = int(config.get("vps_port") or 22)
        user = config.get("vps_user", "root").strip()
        password = config.get("vps_password", "")
        key_data = config.get("vps_key", "")
        log(f"Starting deployment process on single server {host}...", "info")
        cascade_choice = "n"
        node_type_choice = "1"
        if deploy_mode in ["freedom_only", "freedom_component"]:
            cascade_choice = "y"
            node_type_choice = "1"
            default_freedom_client = config.get("freedom_client_name", "").strip() or "local-proxy-node-client"
            xhttp_names = [n.strip() for n in re.split(r'[\s,]+', clients_xhttp_str) if n.strip()]
            if default_freedom_client not in xhttp_names:
                xhttp_names.append(default_freedom_client)
            clients_xhttp_str = " ".join(xhttp_names)
        elif deploy_mode == "proxy_only":
            cascade_choice = "y"
            node_type_choice = "2"

        foreign_sub_url = config.get("foreign_sub_url", "").strip() if deploy_mode == "proxy_only" else ""
        target_domain = config.get("domain", "").strip() or host

        env_vars = {
            "DOMAIN": target_domain,
            "USERNAME": xui_username,
            "USER_PASSWORD": xui_password,
            "XUI_VERSION": xui_version,
            "SECRET_PHRASE": sub_secret,
            "CLIENTS_TCP_LIST": clients_tcp_str,
            "CLIENTS_XHTTP_LIST": clients_xhttp_str,
            "CASCADE_CHOICE": cascade_choice,
            "NODE_TYPE_CHOICE": node_type_choice,
            "FOREIGN_SUB_URL": foreign_sub_url
        }

        ok, out = await _deploy_node(host, port, user, password, key_data, env_vars, log, cancel_check=cancel_check, bundle_source_dir=bundle_dir)
        parsed_xui_url, parsed_clients = parse_deployment_results(out) if ok else ("", [])
        
        final_xui_url = parsed_xui_url or f"https://{target_domain}/{web_base_path}/"
        result_data = {
            "deploy_mode": deploy_mode,
            "xui_url": final_xui_url,
            "xui_username": xui_username,
            "xui_password": xui_password,
            "sub_secret": sub_secret,
            "domain": target_domain,
            "clients": parsed_clients
        }
        return ok, result_data

    # Cascade modes: "cascade" or "cascade_sub"
    freedom_host = config.get("freedom_host", "").strip()
    freedom_port = int(config.get("freedom_port") or 22)
    freedom_user = config.get("freedom_user", "root").strip()
    freedom_password = config.get("freedom_password", "")
    freedom_key = config.get("freedom_key", "")
    freedom_xui_user = config.get("freedom_xui_username", "").strip()
    freedom_xui_pass = config.get("freedom_xui_password", "").strip()
    freedom_secret = config.get("freedom_sub_secret", "").strip()
    freedom_client = config.get("freedom_client_name", "").strip() or "local-proxy-node-client"
    freedom_xui_version = config.get("freedom_xui_version", "").strip() or xui_version

    proxy_host = config.get("proxy_host", "").strip()
    proxy_port = int(config.get("proxy_port") or 22)
    proxy_user = config.get("proxy_user", "root").strip()
    proxy_password = config.get("proxy_password", "")
    proxy_key = config.get("proxy_key", "")
    proxy_xui_user = config.get("proxy_xui_username", "").strip()
    proxy_xui_pass = config.get("proxy_xui_password", "").strip()
    proxy_secret = config.get("proxy_sub_secret", "").strip()
    proxy_xui_version = config.get("proxy_xui_version", "").strip() or xui_version

    proxy_tcp_raw = config.get("proxy_client_tcp_list", "").strip() or tcp_raw
    proxy_xhttp_raw = config.get("proxy_client_xhttp_list", "").strip() or xhttp_raw
    proxy_clients_tcp_str = " ".join([name.strip() for name in re.split(r'[\s,]+', proxy_tcp_raw) if name.strip()])
    proxy_clients_xhttp_str = " ".join([name.strip() for name in re.split(r'[\s,]+', proxy_xhttp_raw) if name.strip()])

    freedom_host_for_ssh = config.get("freedom_host_for_ssh", "").strip()
    proxy_host_for_ssh = config.get("proxy_host_for_ssh", "").strip()

    total_stages = "3" if deploy_mode == "cascade_sub" else "2"

    log("╔════════════════════════════════════════════╗", "info")
    log(f"║ [STAGE 1/{total_stages}] FREEDOM NODE (Foreign Server)    ║", "info")
    log("╠════════════════════════════════════════════╣", "info")
    log(f"║ CURRENTLY DEPLOYING: {freedom_host:35} ║", "info")
    log("╚════════════════════════════════════════════╝", "info")
    freedom_env = {
        "DOMAIN": freedom_host,
        "USERNAME": freedom_xui_user,
        "USER_PASSWORD": freedom_xui_pass,
        "XUI_VERSION": freedom_xui_version,
        "SECRET_PHRASE": freedom_secret,
        "CLIENTS_TCP_LIST": "",
        "CLIENTS_XHTTP_LIST": freedom_client,
        "CASCADE_CHOICE": "y",
        "NODE_TYPE_CHOICE": "1"
    }

    ok1, out1 = await _deploy_node(freedom_host_for_ssh, freedom_port, freedom_user, freedom_password, freedom_key, freedom_env, log, cancel_check=cancel_check, bundle_source_dir=bundle_dir)
    if not ok1:
        log("[ERROR] Stage 1 failed: Could not deploy foreign server.", "error")
        return False, {}
    log("", "success")
    log("✅ [STAGE 1 COMPLETE] Freedom Node deployed successfully!", "success")
    log("", "success")
    freedom_xui_url, freedom_clients = parse_deployment_results(out1)

    freedom_sub_url = ""
    if freedom_clients and len(freedom_clients) > 0:
        freedom_sub_url = freedom_clients[0].get("sub_url", "")
    if not freedom_sub_url:
        freedom_sub_url = f"https://{freedom_host}/{derive_sub_path(freedom_secret)}/{freedom_client}"
    log(f"Cascade subscription URL generated for client '{freedom_client}'.", "info")

    log("╔════════════════════════════════════════════╗", "info")
    log(f"║ [STAGE 2/{total_stages}] PROXY NODE (Local Server)       ║", "info")
    log("╠════════════════════════════════════════════╣", "info")
    log(f"║ CURRENTLY DEPLOYING: {proxy_host:35} ║", "info")
    log("╚════════════════════════════════════════════╝", "info")
    proxy_env = {
        "DOMAIN": proxy_host,
        "USERNAME": proxy_xui_user,
        "USER_PASSWORD": proxy_xui_pass,
        "XUI_VERSION": proxy_xui_version,
        "SECRET_PHRASE": proxy_secret,
        "CLIENTS_TCP_LIST": proxy_clients_tcp_str,
        "CLIENTS_XHTTP_LIST": proxy_clients_xhttp_str,
        "CASCADE_CHOICE": "y",
        "NODE_TYPE_CHOICE": "2",
        "FOREIGN_SUB_URL": freedom_sub_url
    }

    ok2, out2 = await _deploy_node(proxy_host_for_ssh, proxy_port, proxy_user, proxy_password, proxy_key, proxy_env, log, cancel_check=cancel_check, bundle_source_dir=bundle_dir)
    if not ok2:
        log("[ERROR] Stage 2 failed: Could not deploy local server.", "error")
        return False, {}
    log("", "success")
    log("✅ [STAGE 2 COMPLETE] Proxy Node deployed successfully!", "success")
    log("", "success")
    parsed_xui_url, parsed_clients = parse_deployment_results(out2) if ok2 else ("", [])
    proxy_web_path = hashlib.md5(f"{proxy_secret}-panel".encode('utf-8')).hexdigest()[:16]
    final_xui_url = parsed_xui_url or f"https://{proxy_host}/{proxy_web_path}/"
    freedom_web_path = hashlib.md5(f"{freedom_secret}-panel".encode('utf-8')).hexdigest()[:16]
    freedom_final_xui_url = freedom_xui_url or f"https://{freedom_host}/{freedom_web_path}/"

    result_data = {
        "deploy_mode": deploy_mode,
        "is_cascade": True,
        "xui_url": final_xui_url,
        "xui_username": proxy_xui_user,
        "xui_password": proxy_xui_pass,
        "sub_secret": proxy_secret,
        "domain": proxy_host,
        "freedom_xui_url": freedom_final_xui_url,
        "freedom_username": freedom_xui_user,
        "freedom_password": freedom_xui_pass,
        "freedom_sub_secret": freedom_secret,
        "freedom_domain": freedom_host,
        "clients": parsed_clients
    }

    if deploy_mode == "cascade_sub":
        log("╔════════════════════════════════════════════╗", "info")
        log("║ [STAGE 3/3] SUBSCRIPTION SERVER (Relay)   ║", "info")
        log("╠════════════════════════════════════════════╣", "info")
        log(f"║ CURRENTLY DEPLOYING: {config.get('sub_vps_host', '').strip():35} ║", "info")
        log("╚════════════════════════════════════════════╝", "info")

        sub_host = config.get("sub_vps_host", "").strip()
        sub_port = int(config.get("sub_vps_port") or 22)
        sub_user = config.get("sub_vps_user", "root").strip() or "root"
        sub_password = config.get("sub_vps_password", "")
        sub_key = config.get("sub_vps_key", "")
        sub_domain = config.get("sub_domain", "").strip() or sub_host
        sub_secret_path = config.get("sub_secret_path", "").strip()
        sub_secret_path = sub_secret_path.strip("/")

        if not sub_host:
            log("[ERROR] Stage 3 failed: Subscription Server host address is required.", "error")
            return False, {}

        proxy_node_sub_base = ""
        if parsed_clients and parsed_clients[0].get("sub_url"):
            proxy_node_sub_base = parsed_clients[0]["sub_url"].rsplit("/", 1)[0]
        if not proxy_node_sub_base:
            proxy_node_sub_base = f"https://{proxy_host}/{derive_sub_path(proxy_secret)}"
        freedom_node_sub_base = ""
        if freedom_sub_url:
            freedom_node_sub_base = freedom_sub_url.rsplit("/", 1)[0]
        if not freedom_node_sub_base:
            freedom_node_sub_base = f"https://{freedom_host}/{derive_sub_path(freedom_secret)}"

        proxy_client_names = [n.strip() for n in re.split(r'[\s,]+', f"{proxy_clients_tcp_str} {proxy_clients_xhttp_str}") if n.strip()]
        freedom_client_names = [freedom_client]

        sub_admin_user = config.get("sub_admin_user", "").strip()
        sub_admin_password = config.get("sub_admin_password", "").strip()

        resolved_proxy, resolved_freedom, extra_sub_env = resolve_sub_server_urls(
            proxy_node_sub_base, freedom_node_sub_base,
        )

        sub_env = {
            "DOMAIN": sub_domain,
            "SECRET_SUB_PATH": sub_secret_path,
            "RUSSIAN_SUB_URL": resolved_proxy,
            "FOREIGN_SUB_URL": resolved_freedom,
            "PROXY_CLIENTS": " ".join(proxy_client_names),
            "FREEDOM_CLIENTS": " ".join(freedom_client_names),
            "ADMIN_USER": sub_admin_user,
            "ADMIN_PASSWORD": sub_admin_password,
            **extra_sub_env,
        }

        ok3, out3 = await _deploy_sub_server(sub_host, sub_port, sub_user, sub_password, sub_key, sub_env, log, cancel_check=cancel_check, bundle_source_dir=bundle_dir)
        if not ok3:
            log("[ERROR] Stage 3 failed: Subscription Server deployment failed.", "error")
            return False, {}

        log("", "success")
        log("✅ [STAGE 3 COMPLETE] Subscription Server deployed successfully!", "success")
        log("", "success")

        base_sub_url = f"https://{sub_domain}/{sub_secret_path}"
        result_data["sub_domain"] = sub_domain
        result_data["sub_secret_path"] = sub_secret_path
        result_data["sub_base_url"] = base_sub_url
        result_data["sub_admin_user"] = sub_admin_user
        result_data["sub_admin_password"] = sub_admin_password

        # Attach sub_url to client objects if available
        for cl in parsed_clients:
            cl["sub_server_url"] = f"{base_sub_url}/{cl['name']}"

    log("╔════════════════════════════════════════════╗", "success")
    log("║         🎉 ALL STAGES COMPLETED! 🎉         ║", "success")
    log("╚════════════════════════════════════════════╝", "success")
    log("", "success")
    log(f"Panel 1 (Freedom Node): {freedom_final_xui_url}", "success")
    log(f"  - Admin User: {freedom_xui_user}", "success")
    log(f"  - Admin Password: ••••••••", "success")
    log(f"Panel 2 (Proxy Node): {final_xui_url}", "success")
    log(f"  - Admin User: {proxy_xui_user}", "success")
    log(f"  - Admin Password: ••••••••", "success")
    if deploy_mode == "cascade_sub":
        log(f"Subscription Server: https://{result_data['sub_domain']}/{result_data['sub_secret_path']}/<username>", "success")
        log(f"  - Admin: {result_data.get('sub_admin_user', 'admin')} / password: ••••••••", "success")
    log("=========================================", "success")
    return True, result_data
