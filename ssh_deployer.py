import asyncio
import base64
import hashlib
import io
import json
import os
import re
import secrets
import shlex
import string
import sys
import tarfile
import tempfile
from typing import Callable, Dict, Any, Optional, List, Tuple

ANSI_ESCAPE = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')

def strip_ansi(text: str) -> str:
    return ANSI_ESCAPE.sub('', text)

def generate_random_string(length: int = 16) -> str:
    alphabet = string.ascii_letters + string.digits
    return ''.join(secrets.choice(alphabet) for _ in range(length))

def get_bundle_bytes() -> bytes:
    buf = io.BytesIO()
    repo_dir = os.path.dirname(os.path.abspath(__file__))
    with tarfile.open(fileobj=buf, mode='w:gz') as tar:
        for root, dirs, files in os.walk(repo_dir):
            if '.git' in root or '.python_env' in root or '__pycache__' in root or (os.sep + 'panel' + os.sep + 'static') in root:
                continue
            for file in files:
                if file.endswith('.pyc') or file == 'setup_backup.yml':
                    continue
                full_path = os.path.join(root, file)
                rel_path = os.path.relpath(full_path, repo_dir)
                tar.add(full_path, arcname=rel_path)
    return buf.getvalue()

def parse_deployment_results(output_text: str) -> Tuple[str, List[Dict[str, str]]]:
    clients = []
    current_client = None
    xui_url = ""
    lines = output_text.splitlines()
    for i, line in enumerate(lines):
        line = line.strip()
        if "3x-UI" in line or "panel is available at" in line or "панель доступна на" in line:
            for j in range(i+1, min(i+5, len(lines))):
                candidate = lines[j].strip()
                if candidate.startswith("https://") or candidate.startswith("http://"):
                    xui_url = candidate
                    break
        if line.startswith("Client:") or line.startswith("Клиент:"):
            if current_client:
                clients.append(current_client)
            cname = line.split(":", 1)[1].strip()
            current_client = {"name": cname, "sub_url": "", "tcp_url": "", "xhttp_url": ""}
        elif current_client:
            if line.startswith("https://") or line.startswith("http://"):
                if not current_client["sub_url"]:
                    current_client["sub_url"] = line
            elif line.startswith("vless://"):
                if "type=xhttp" in line:
                    current_client["xhttp_url"] = line
                else:
                    current_client["tcp_url"] = line
    if current_client:
        clients.append(current_client)
    return xui_url, clients

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
            while True:
                if self.cancel_check and self.cancel_check():
                    try:
                        proc.terminate()
                        try:
                            proc.kill()
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
                    if log_callback:
                        log_callback(decoded)
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


async def _ensure_remote_docker(deployer: SSHDeployer, log: Callable[[str, str], None]) -> tuple[bool, str]:
    if deployer.cancel_check and deployer.cancel_check():
        return False, "Cancelled by user"

    rc, _ = await deployer.exec_command("which docker", lambda m: log(m, "info"))
    if rc == 0:
        await deployer.exec_command("systemctl start docker 2>/dev/null || true; systemctl enable docker 2>/dev/null || true", lambda m: log(m, "info"))
        return True, "Docker is already installed"

    if deployer.cancel_check and deployer.cancel_check():
        return False, "Cancelled by user"

    log("Checking package manager status on remote server...", "info")
    wait_lock_cmd = (
        "while fuser /var/lib/dpkg/lock-frontend /var/lib/dpkg/lock /var/lib/apt/lists/lock >/dev/null 2>&1 || pgrep -x 'apt-get|dpkg|unattended-upgr' >/dev/null 2>&1; do "
        "  echo '[..] Package manager is locked by system process. Waiting 5 seconds...'; "
        "  sleep 5; "
        "done"
    )
    rc, out = await deployer.exec_command(wait_lock_cmd, lambda m: log(m, "info"))
    if rc != 0 or (deployer.cancel_check and deployer.cancel_check()):
        return False, out or "Cancelled by user"

    log("Installing Docker using official get.docker.com script...", "info")
    install_docker_cmd = "curl -fsSL https://get.docker.com | sh"
    rc, out = await deployer.exec_command(install_docker_cmd, lambda m: log(m, "info"))
    if rc != 0 or (deployer.cancel_check and deployer.cancel_check()):
        err_msg = f"Failed to install Docker: {out}"
        log(f"[ERROR] {err_msg}", "error")
        return False, err_msg

    log("Configuring Docker daemon & registry mirrors...", "info")
    mirror_cmd = (
        "mkdir -p /etc/docker && "
        "echo '{\"registry-mirrors\": [\"https://dh-mirror.gitverse.ru\"]}' > /etc/docker/daemon.json && "
        "systemctl daemon-reload 2>/dev/null || true; "
        "systemctl start docker && systemctl enable docker"
    )
    rc, out = await deployer.exec_command(mirror_cmd, lambda m: log(m, "info"))
    if rc != 0 or (deployer.cancel_check and deployer.cancel_check()):
        return False, out or "Cancelled by user"

    rc, _ = await deployer.exec_command("which docker", lambda m: log(m, "info"))
    if rc != 0:
        return False, "Docker installation completed but 'docker' binary was not found in PATH."

    return True, "Docker installed successfully"


async def _perform_remote_backup(deployer: SSHDeployer, backup_name: str, log: Callable[[str, str], None]) -> tuple[bool, str, float]:
    """Create a backup archive on the remote server, download it locally via SCP, and clean up.

    Returns (success, local_backup_path, file_size_mb).
    """
    import datetime as _dt

    repo_root = os.path.dirname(os.path.abspath(__file__))
    backups_dir = os.path.join(repo_root, "backups")
    os.makedirs(backups_dir, exist_ok=True)
    local_backup_path = os.path.join(backups_dir, backup_name)

    log("Creating backup archive on remote server...", "info")
    remote_script = (
        "set -e\n"
        "WORK_DIR=\"/opt/3x-ui-bootstRUp\"\n"
        "if [ ! -d \"$WORK_DIR\" ]; then\n"
        "  if [ -d \"./working\" ]; then WORK_DIR=\".\"; else WORK_DIR=\"$(pwd)\"; fi\n"
        "fi\n"
        "cd \"$WORK_DIR\"\n"
        "rm -rf /tmp/remote_server_backup /tmp/server_backup.tar.gz\n"
        "if [ -f \"panel_backup.sh\" ]; then\n"
        "  bash panel_backup.sh /tmp/remote_server_backup\n"
        "else\n"
        "  mkdir -p /tmp/remote_server_backup\n"
        "  [ -d \"working/3x-ui\" ] && cp -r working/3x-ui /tmp/remote_server_backup/3x-ui || true\n"
        "  [ -d \"working/3xui\" ] && cp -r working/3xui /tmp/remote_server_backup/3xui || true\n"
        "  [ -d \"working/docker-compose\" ] && cp -r working/docker-compose /tmp/remote_server_backup/docker-compose || true\n"
        "  [ -d \"working/nginx-decoy\" ] && cp -r working/nginx-decoy /tmp/remote_server_backup/nginx-decoy || true\n"
        "  [ -d \"working/caddy\" ] && cp -r working/caddy /tmp/remote_server_backup/caddy || true\n"
        "fi\n"
        "tar -czf /tmp/server_backup.tar.gz -C /tmp/remote_server_backup .\n"
        "rm -rf /tmp/remote_server_backup\n"
    )

    rc, out = await deployer.exec_command(f"bash -c {shlex.quote(remote_script)}", lambda m: log(m, "info"))
    if rc != 0:
        log(f"[ERROR] Remote backup creation failed: {out}", "error")
        return False, "", 0.0

    log(f"⬇️ Downloading backup archive via SCP to ./backups/{backup_name}...", "info")
    rc_scp, scp_out = await deployer.download_file("/tmp/server_backup.tar.gz", local_backup_path, lambda m: log(m, "info"))

    # Cleanup remote archive
    await deployer.exec_command("rm -f /tmp/server_backup.tar.gz")

    if rc_scp != 0 or not os.path.exists(local_backup_path):
        log(f"[ERROR] SCP download failed: {scp_out}", "error")
        return False, "", 0.0

    file_size_bytes = os.path.getsize(local_backup_path)
    file_size_mb = round(file_size_bytes / (1024 * 1024), 2)

    return True, local_backup_path, file_size_mb


async def _deploy_node(host: str, port: int, user: str, password: str, key_data: str, env_vars: Dict[str, str], log: Callable[[str, str], None], cancel_check: Optional[Callable[[], bool]] = None) -> tuple[bool, str]:
    remote_dir = "/opt/3x-ui-bootstRUp"
    async with SSHDeployer(host, port, user, password, key_data, cancel_check=cancel_check) as deployer:
        log(f"Connecting to {host}:{port}...", "info")
        ok, msg = await deployer.test_connection()
        if not ok:
            log(f"SSH test failed for {host}: {msg}", "error")
            return False, ""

        log(f"Checking and installing Docker on {host}...", "info")
        ok_doc, doc_msg = await _ensure_remote_docker(deployer, log)
        if not ok_doc:
            log(f"[ERROR] Docker setup failed on {host}: {doc_msg}", "error")
            return False, ""

        log(f"Syncing local files to {host}...", "info")
        bundle_bytes = get_bundle_bytes()
        sync_cmd = f"mkdir -p {remote_dir} && tar -xzf - -C {remote_dir}"
        rc, sync_out = await deployer.exec_command(sync_cmd, lambda m: log(m, "info"), stdin_data=bundle_bytes)
        if rc != 0:
            log(f"[ERROR] Failed to transfer files to {host}: {sync_out}", "error")
            return False, ""

        log(f"Executing setup.sh script on {host}...", "info")
        
        env_str_parts = []
        for k, v in env_vars.items():
            if v:
                env_str_parts.append(f"{k}={shlex.quote(str(v))}")
        env_str = " ".join(env_str_parts)
        remote_cmd = f"cd {shlex.quote(remote_dir)} && {env_str} bash panel/setup.sh"
        rc, out = await deployer.exec_command(remote_cmd, lambda m: log(m, "info"))
        if rc == 0:
            return True, out
        return False, out

async def _deploy_sub_server(host: str, port: int, user: str, password: str, key_data: str, env_vars: Dict[str, str], log: Callable[[str, str], None], cancel_check: Optional[Callable[[], bool]] = None) -> tuple[bool, str]:
    remote_dir = "/opt/3x-ui-bootstRUp"
    async with SSHDeployer(host, port, user, password, key_data, cancel_check=cancel_check) as deployer:
        log(f"Connecting to Subscription Server on {host}:{port}...", "info")
        ok, msg = await deployer.test_connection()
        if not ok:
            log(f"SSH test failed for Subscription Server {host}: {msg}", "error")
            return False, ""

        log(f"Checking and installing Docker on {host}...", "info")
        ok_doc, doc_msg = await _ensure_remote_docker(deployer, log)
        if not ok_doc:
            log(f"[ERROR] Docker setup failed on Subscription Server {host}: {doc_msg}", "error")
            return False, ""

        log(f"Syncing local files to Subscription Server {host}...", "info")
        bundle_bytes = get_bundle_bytes()
        sync_cmd = f"mkdir -p {remote_dir} && tar -xzf - -C {remote_dir}"
        rc, sync_out = await deployer.exec_command(sync_cmd, lambda m: log(m, "info"), stdin_data=bundle_bytes)
        if rc != 0:
            log(f"[ERROR] Failed to transfer files to Subscription Server {host}: {sync_out}", "error")
            return False, ""

        log(f"Executing sub-server/setup.sh script on {host}...", "info")
        env_str_parts = []
        for k, v in env_vars.items():
            if v:
                env_str_parts.append(f"{k}={shlex.quote(str(v))}")
        env_str = " ".join(env_str_parts)
        remote_cmd = f"cd {shlex.quote(remote_dir)} && {env_str} bash sub-server/setup.sh"
        rc, out = await deployer.exec_command(remote_cmd, lambda m: log(m, "info"))
        if rc == 0:
            return True, out
        return False, out

async def run_deployment(config: Dict[str, Any], log_callback: Callable[[str, str], None], cancel_check: Optional[Callable[[], bool]] = None) -> Tuple[bool, Dict[str, Any]]:
    def log(msg: str, level: str = "info"):
        log_callback(msg, level)

    deploy_mode = config.get("deploy_mode", "").strip()
    if not deploy_mode:
        deploy_mode = "cascade" if config.get("is_cascade", False) else "single"

    email = config.get("email", "").strip()
    xui_username = config.get("xui_username", "admin").strip()
    xui_password = config.get("xui_password", "").strip() or generate_random_string(12)
    xui_version = config.get("xui_version", "").strip() or "3.6.0"
    xui_web_port = config.get("xui_web_port", "").strip()
    xui_sub_port = config.get("xui_sub_port", "").strip()
    sub_secret = config.get("sub_secret", "").strip() or generate_random_string(16)

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
            log(f"Local backup location: ./backups/{backup_name} ({file_size_mb} MB)", "success")
            log("=========================================", "success")

            return True, {
                "deploy_mode": "backup",
                "backup_host": host,
                "backup_name": backup_name,
                "backup_path": f"./backups/{backup_name}",
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

        if not host:
            log("[ERROR] Target domain host is required for recovery mode.", "error")
            return False, {}

        if not backup_filename:
            log("[ERROR] Backup file must be selected for recovery mode.", "error")
            return False, {}

        repo_root = os.path.dirname(os.path.abspath(__file__))
        local_backup_path = os.path.join(repo_root, "backups", os.path.basename(backup_filename))

        if not os.path.isfile(local_backup_path):
            log(f"[ERROR] Selected backup archive '{backup_filename}' not found in ./backups/", "error")
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

            log(f"Checking and installing dependencies and Docker on {host}...", "info")
            ok_doc, doc_msg = await _ensure_remote_docker(deployer, log)
            if not ok_doc:
                log(f"[ERROR] Docker setup failed: {doc_msg}", "error")
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
                "    sed -i \"s/$OLD_DOMAIN/$NEW_DOM/g\" \"$CADDY_FILE\"\n"
                "    [ -f \"working/nginx-decoy/default.conf\" ] && sed -i \"s/$OLD_DOMAIN/$NEW_DOM/g\" \"working/nginx-decoy/default.conf\" || true\n"
                "    find working/3x-ui/ -type f -name \"*.json\" -exec sed -i \"s/$OLD_DOMAIN/$NEW_DOM/g\" {} + 2>/dev/null || true\n"
                "    rm -rf working/.caddy_data 2>/dev/null || true\n"
                "    docker volume rm caddy_data 2>/dev/null || true\n"
                "  fi\n"
                "  WEB_PATH=$(grep -oE '@web_base_path path /[^ /]+' \"$CADDY_FILE\" | head -n 1 | awk '{print $3}' | tr -d '/' || true)\n"
                "  if [ -n \"$WEB_PATH\" ]; then\n"
                "    echo \"RECOVERY_WEB_PATH=$WEB_PATH\"\n"
                "  fi\n"
                "fi\n"
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

            web_base_path = ""
            try:
                import tarfile
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

            if not web_base_path:
                m_path_out = re.search(r'RECOVERY_WEB_PATH=([A-Za-z0-9_-]+)', out)
                if m_path_out:
                    web_base_path = m_path_out.group(1)

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
        target_version = (config.get("update_xui_version") or config.get("xui_version") or "3.6.0").strip()

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

            log(f"✅ Pre-update backup saved: ./backups/{backup_name} ({file_size_mb} MB)", "success")
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
            log(f"Pre-update backup: ./backups/{backup_name} ({file_size_mb} MB)", "success")
            log("=========================================", "success")

            return True, {
                "deploy_mode": "update_3xui",
                "update_host": host,
                "xui_version": target_version,
                "xui_url": xui_url,
                "backup_name": backup_name,
                "backup_path": f"./backups/{backup_name}",
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
                    "docker compose -f working/docker-compose/docker-compose.yml down\n"
                    "docker compose -f working/docker-compose/docker-compose.yml up -d\n"
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

    # Standalone Subscription Server Mode
    if deploy_mode == "sub_only":
        sub_host = config.get("sub_vps_host", "").strip() or config.get("vps_host", "").strip()
        sub_port = int(config.get("sub_vps_port", config.get("vps_port", 22)))
        sub_user = config.get("sub_vps_user", "").strip() or config.get("vps_user", "root").strip()
        sub_password = config.get("sub_vps_password", config.get("vps_password", ""))
        sub_key = config.get("sub_vps_key", config.get("vps_key", ""))
        sub_domain = config.get("sub_domain", "").strip() or sub_host
        sub_secret_path = config.get("sub_secret_path", "subs").strip() or "subs"
        sub_secret_path = sub_secret_path.strip("/")

        sub_russian_url = config.get("sub_russian_url", "").strip()
        sub_foreign_url = config.get("sub_foreign_url", "").strip()

        proxy_raw = config.get("sub_proxy_clients", "").strip()
        freedom_raw = config.get("sub_freedom_clients", "").strip()
        proxy_clients = [n.strip() for n in re.split(r'[\s,]+', proxy_raw) if n.strip()]
        freedom_clients = [n.strip() for n in re.split(r'[\s,]+', freedom_raw) if n.strip()]

        log(f"Starting deployment of Subscription Server on {sub_host}...", "info")
        sub_env = {
            "DOMAIN": sub_domain,
            "SECRET_SUB_PATH": sub_secret_path,
            "RUSSIAN_SUB_URL": sub_russian_url,
            "FOREIGN_SUB_URL": sub_foreign_url,
            "PROXY_CLIENTS": " ".join(proxy_clients),
            "FREEDOM_CLIENTS": " ".join(freedom_clients)
        }

        ok_sub, out_sub = await _deploy_sub_server(sub_host, sub_port, sub_user, sub_password, sub_key, sub_env, log, cancel_check=cancel_check)
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
        log("=========================================", "success")

        result_data = {
            "deploy_mode": "sub_only",
            "sub_domain": sub_domain,
            "sub_secret_path": sub_secret_path,
            "sub_base_url": base_sub_url,
            "clients": sub_clients
        }
        return True, result_data

    tcp_raw = config.get("client_tcp_list", "").strip()
    xhttp_raw = config.get("client_xhttp_list", "").strip()
    clients_tcp_str = " ".join([name.strip() for name in re.split(r'[\s,]+', tcp_raw) if name.strip()])
    clients_xhttp_str = " ".join([name.strip() for name in re.split(r'[\s,]+', xhttp_raw) if name.strip()])

    web_base_path = hashlib.md5(f"{sub_secret}-panel".encode('utf-8')).hexdigest()[:16]
    log("Generated secure deployment configuration.", "info")

    if deploy_mode in ["single", "proxy_only", "freedom_only"]:
        host = config.get("vps_host", "").strip()
        port = int(config.get("vps_port", 22))
        user = config.get("vps_user", "root").strip()
        password = config.get("vps_password", "")
        key_data = config.get("vps_key", "")
        log(f"Starting deployment process on single server {host}...", "info")
        cascade_choice = "n"
        node_type_choice = "1"
        if deploy_mode == "freedom_only":
            cascade_choice = "y"
            node_type_choice = "1"
        elif deploy_mode == "proxy_only":
            cascade_choice = "y"
            node_type_choice = "2"
            
        env_vars = {
            "DOMAIN": host,
            "EMAIL": email,
            "USERNAME": xui_username,
            "USER_PASSWORD": xui_password,
            "XUI_VERSION": xui_version,
            "XUI_WEB_PORT": xui_web_port,
            "XUI_SUB_PORT": xui_sub_port,
            "SECRET_PHRASE": sub_secret,
            "CLIENTS_TCP_LIST": clients_tcp_str,
            "CLIENTS_XHTTP_LIST": clients_xhttp_str,
            "CASCADE_CHOICE": cascade_choice,
            "NODE_TYPE_CHOICE": node_type_choice,
            "FOREIGN_SUB_URL": ""
        }
        ok, out = await _deploy_node(host, port, user, password, key_data, env_vars, log, cancel_check=cancel_check)
        parsed_xui_url, parsed_clients = parse_deployment_results(out) if ok else ("", [])
        
        final_xui_url = parsed_xui_url or f"https://{host}/{web_base_path}/"
        result_data = {
            "deploy_mode": deploy_mode,
            "xui_url": final_xui_url,
            "xui_username": xui_username,
            "xui_password": xui_password,
            "sub_secret": sub_secret,
            "domain": host,
            "clients": parsed_clients
        }
        return ok, result_data

    # Cascade modes: "cascade" or "cascade_sub"
    freedom_host = config.get("freedom_host", "").strip()
    freedom_port = int(config.get("freedom_port", 22))
    freedom_user = config.get("freedom_user", "root").strip()
    freedom_password = config.get("freedom_password", "")
    freedom_key = config.get("freedom_key", "")
    freedom_xui_user = config.get("freedom_xui_username", "").strip() or xui_username
    freedom_xui_pass = config.get("freedom_xui_password", "").strip() or xui_password
    freedom_secret = config.get("freedom_sub_secret", "").strip() or sub_secret
    freedom_client = config.get("freedom_client_name", "").strip() or "local-proxy-node-client"
    freedom_xui_version = config.get("freedom_xui_version", "").strip() or xui_version

    proxy_host = config.get("proxy_host", "").strip()
    proxy_port = int(config.get("proxy_port", 22))
    proxy_user = config.get("proxy_user", "root").strip()
    proxy_password = config.get("proxy_password", "")
    proxy_key = config.get("proxy_key", "")
    proxy_xui_user = config.get("proxy_xui_username", "").strip() or xui_username
    proxy_xui_pass = config.get("proxy_xui_password", "").strip() or xui_password
    proxy_secret = config.get("proxy_sub_secret", "").strip() or sub_secret
    proxy_xui_version = config.get("proxy_xui_version", "").strip() or xui_version

    proxy_tcp_raw = config.get("proxy_client_tcp_list", "").strip() or tcp_raw
    proxy_xhttp_raw = config.get("proxy_client_xhttp_list", "").strip() or xhttp_raw
    proxy_clients_tcp_str = " ".join([name.strip() for name in re.split(r'[\s,]+', proxy_tcp_raw) if name.strip()])
    proxy_clients_xhttp_str = " ".join([name.strip() for name in re.split(r'[\s,]+', proxy_xhttp_raw) if name.strip()])

    total_stages = "3" if deploy_mode == "cascade_sub" else "2"

    log("=========================================", "info")
    log(f"[STAGE 1/{total_stages}] Deploying foreign server (Freedom Node) on {freedom_host}...", "info")
    log("=========================================", "info")
    freedom_env = {
        "DOMAIN": freedom_host,
        "EMAIL": email,
        "USERNAME": freedom_xui_user,
        "USER_PASSWORD": freedom_xui_pass,
        "XUI_VERSION": freedom_xui_version,
        "XUI_WEB_PORT": xui_web_port,
        "XUI_SUB_PORT": xui_sub_port,
        "SECRET_PHRASE": freedom_secret,
        "CLIENTS_TCP_LIST": "",
        "CLIENTS_XHTTP_LIST": freedom_client,
        "CASCADE_CHOICE": "y",
        "NODE_TYPE_CHOICE": "1"
    }
    ok1, out1 = await _deploy_node(freedom_host, freedom_port, freedom_user, freedom_password, freedom_key, freedom_env, log, cancel_check=cancel_check)
    if not ok1:
        log("[ERROR] Stage 1 failed: Could not deploy foreign server.", "error")
        return False, {}
    log("[OK] Foreign server (Freedom Node) deployed successfully!", "success")
    freedom_xui_url, freedom_clients = parse_deployment_results(out1)

    freedom_sub_url = ""
    if freedom_clients and len(freedom_clients) > 0:
        freedom_sub_url = freedom_clients[0].get("sub_url", "")
    if not freedom_sub_url:
        freedom_sub_port_str = xui_sub_port if xui_sub_port else "2096"
        freedom_sub_url = f"https://{freedom_host}:{freedom_sub_port_str}/{freedom_secret}/{freedom_client}"
    log(f"Cascade subscription URL generated for client '{freedom_client}'.", "info")

    log("=========================================", "info")
    log(f"[STAGE 2/{total_stages}] Deploying local server (Proxy Node) on {proxy_host}...", "info")
    log("=========================================", "info")
    proxy_env = {
        "DOMAIN": proxy_host,
        "EMAIL": email,
        "USERNAME": proxy_xui_user,
        "USER_PASSWORD": proxy_xui_pass,
        "XUI_VERSION": proxy_xui_version,
        "XUI_WEB_PORT": xui_web_port,
        "XUI_SUB_PORT": xui_sub_port,
        "SECRET_PHRASE": proxy_secret,
        "CLIENTS_TCP_LIST": proxy_clients_tcp_str,
        "CLIENTS_XHTTP_LIST": proxy_clients_xhttp_str,
        "CASCADE_CHOICE": "y",
        "NODE_TYPE_CHOICE": "2",
        "FOREIGN_SUB_URL": freedom_sub_url
    }
    ok2, out2 = await _deploy_node(proxy_host, proxy_port, proxy_user, proxy_password, proxy_key, proxy_env, log, cancel_check=cancel_check)
    if not ok2:
        log("[ERROR] Stage 2 failed: Could not deploy local server.", "error")
        return False, {}
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
        log("=========================================", "info")
        log(f"[STAGE 3/3] Deploying Subscription Server...", "info")
        log("=========================================", "info")

        sub_host = config.get("sub_vps_host", "").strip()
        sub_port = int(config.get("sub_vps_port", 22))
        sub_user = config.get("sub_vps_user", "root").strip() or "root"
        sub_password = config.get("sub_vps_password", "")
        sub_key = config.get("sub_vps_key", "")
        sub_domain = config.get("sub_domain", "").strip() or sub_host
        sub_secret_path = config.get("sub_secret_path", "subs").strip() or "subs"
        sub_secret_path = sub_secret_path.strip("/")

        if not sub_host:
            log("[ERROR] Stage 3 failed: Subscription Server host address is required.", "error")
            return False, {}

        node_sub_port_str = xui_sub_port if xui_sub_port else "2096"
        proxy_node_sub_base = f"https://{proxy_host}:{node_sub_port_str}/{proxy_secret}"
        freedom_node_sub_base = f"https://{freedom_host}:{node_sub_port_str}/{freedom_secret}"

        proxy_client_names = [n.strip() for n in re.split(r'[\s,]+', f"{proxy_clients_tcp_str} {proxy_clients_xhttp_str}") if n.strip()]
        freedom_client_names = [freedom_client]

        sub_env = {
            "DOMAIN": sub_domain,
            "SECRET_SUB_PATH": sub_secret_path,
            "RUSSIAN_SUB_URL": proxy_node_sub_base,
            "FOREIGN_SUB_URL": freedom_node_sub_base,
            "PROXY_CLIENTS": " ".join(proxy_client_names),
            "FREEDOM_CLIENTS": " ".join(freedom_client_names)
        }

        ok3, out3 = await _deploy_sub_server(sub_host, sub_port, sub_user, sub_password, sub_key, sub_env, log, cancel_check=cancel_check)
        if not ok3:
            log("[ERROR] Stage 3 failed: Subscription Server deployment failed.", "error")
            return False, {}

        base_sub_url = f"https://{sub_domain}/{sub_secret_path}"
        result_data["sub_domain"] = sub_domain
        result_data["sub_secret_path"] = sub_secret_path
        result_data["sub_base_url"] = base_sub_url

        # Attach sub_url to client objects if available
        for cl in parsed_clients:
            cl["sub_server_url"] = f"{base_sub_url}/{cl['name']}"

    log("=========================================", "success")
    log("🎉 DEPLOYMENT COMPLETED SUCCESSFULLY!", "success")
    log(f"Panel 1 (Freedom Node): {freedom_final_xui_url}", "success")
    log(f"  - Admin User: {freedom_xui_user}", "success")
    log(f"  - Admin Password: ••••••••", "success")
    log(f"Panel 2 (Proxy Node): {final_xui_url}", "success")
    log(f"  - Admin User: {proxy_xui_user}", "success")
    log(f"  - Admin Password: ••••••••", "success")
    if deploy_mode == "cascade_sub":
        log(f"Subscription Server: https://{result_data['sub_domain']}/{result_data['sub_secret_path']}/<username>", "success")
    log("=========================================", "success")
    return True, result_data