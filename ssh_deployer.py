import asyncio
import base64
import hashlib
import io
import json
import os
import re
import secrets
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
            if '.git' in root or '.python_env' in root or '__pycache__' in root or 'static' in root:
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
    def __init__(self, host: str, port: int = 22, user: str = "root", password: str = "", key_data: str = ""):
        self.host = host
        self.port = str(port)
        self.user = user
        self.password = password
        self.key_data = key_data
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
            if sys.platform == "win32":
                tf_pass = tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.bat')
                tf_pass.write(f'@echo {self.password}\n')
                tf_pass.close()
                self._askpass_file = tf_pass.name
            else:
                tf_pass = tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.sh')
                tf_pass.write(f'#!/bin/sh\necho "{self.password}"\n')
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
            "-p", self.port
        ]
        
        env = os.environ.copy()
        if self._key_file:
            cmd.extend(["-i", self._key_file])
        elif self._askpass_file:
            env["SSH_ASKPASS"] = self._askpass_file
            env["SSH_ASKPASS_REQUIRE"] = "force"
            env["DISPLAY"] = "dummy:0"
        target = f"{self.user}@{self.host}"
        cmd.extend([target, remote_cmd])
        return cmd, env
    async def exec_command(self, remote_cmd: str, log_callback: Optional[Callable[[str], None]] = None, stdin_data: Optional[bytes] = None) -> tuple[int, str]:
        cmd, env = self._build_ssh_cmd_and_env(remote_cmd)
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdin=asyncio.subprocess.PIPE if stdin_data else None,
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
                line = await proc.stdout.readline()
                if not line:
                    break
                decoded = strip_ansi(line.decode('utf-8', errors='replace')).rstrip()
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

async def _deploy_node(host: str, port: int, user: str, password: str, key_data: str, env_vars: Dict[str, str], log: Callable[[str, str], None]) -> tuple[bool, str]:
    remote_dir = "/opt/3x-ui-bootstRUp"
    async with SSHDeployer(host, port, user, password, key_data) as deployer:
        log(f"Connecting to {host}:{port}...", "info")
        ok, msg = await deployer.test_connection()
        if not ok:
            log(f"SSH test failed for {host}: {msg}", "error")
            return False, ""

        log(f"Checking and installing Docker on {host}...", "info")
        rc, _ = await deployer.exec_command("which docker", lambda m: log(m, "info"))
        if rc != 0:
            await deployer.exec_command("curl -fsSL https://get.docker.com | sh", lambda m: log(m, "info"))
        await deployer.exec_command("systemctl start docker && systemctl enable docker", lambda m: log(m, "info"))

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
                env_str_parts.append(f"{k}='{v}'")
        env_str = " ".join(env_str_parts)
        remote_cmd = f"cd '{remote_dir}' && {env_str} bash setup.sh"
        rc, out = await deployer.exec_command(remote_cmd, lambda m: log(m, "info"))
        if rc == 0:
            return True, out
        return False, out

async def run_deployment(config: Dict[str, Any], log_callback: Callable[[str, str], None]) -> Tuple[bool, Dict[str, Any]]:
    def log(msg: str, level: str = "info"):
        log_callback(msg, level)

    is_cascade = config.get("is_cascade", False)
    email = config.get("email", "").strip()
    xui_username = config.get("xui_username", "admin").strip()
    xui_password = config.get("xui_password", "").strip() or generate_random_string(12)
    xui_version = config.get("xui_version", "").strip() or "3.6.0"
    xui_web_port = config.get("xui_web_port", "").strip()
    xui_sub_port = config.get("xui_sub_port", "").strip()
    sub_secret = config.get("sub_secret", "").strip() or generate_random_string(16)
    
    tcp_raw = config.get("client_tcp_list", "").strip()
    xhttp_raw = config.get("client_xhttp_list", "").strip()
    clients_tcp_str = " ".join([name.strip() for name in re.split(r'[\s,]+', tcp_raw) if name.strip()])
    clients_xhttp_str = " ".join([name.strip() for name in re.split(r'[\s,]+', xhttp_raw) if name.strip()])

    web_base_path = hashlib.md5(f"{sub_secret}-panel".encode('utf-8')).hexdigest()[:16]
    log("Generated secure deployment configuration.", "info")

    if not is_cascade:
        # --- Single Server Deployment ---
        host = config.get("vps_host", "").strip()
        port = int(config.get("vps_port", 22))
        user = config.get("vps_user", "root").strip()
        password = config.get("vps_password", "")
        key_data = config.get("vps_key", "")
        log(f"Starting deployment process on single server {host}...", "info")
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
            "CASCADE_CHOICE": "n",
            "NODE_TYPE_CHOICE": "1"
        }
        ok, out = await _deploy_node(host, port, user, password, key_data, env_vars, log)
        parsed_xui_url, parsed_clients = parse_deployment_results(out) if ok else ("", [])
        
        final_xui_url = parsed_xui_url or f"https://{host}/{web_base_path}/"
        result_data = {
            "xui_url": final_xui_url,
            "xui_username": xui_username,
            "xui_password": xui_password,
            "sub_secret": sub_secret,
            "domain": host,
            "clients": parsed_clients
        }
        return ok, result_data
    else:
        # --- 2-Stage Automated Cascade Deployment ---
        freedom_host = config.get("freedom_host", "").strip()
        freedom_port = int(config.get("freedom_port", 22))
        freedom_user = config.get("freedom_user", "root").strip()
        freedom_password = config.get("freedom_password", "")
        freedom_xui_user = config.get("freedom_xui_username", "").strip() or xui_username
        freedom_xui_pass = config.get("freedom_xui_password", "").strip() or xui_password
        freedom_secret = config.get("freedom_sub_secret", "").strip() or sub_secret
        freedom_client = config.get("freedom_client_name", "").strip() or "local-proxy-node-client"
        freedom_xui_version = config.get("freedom_xui_version", "").strip() or xui_version

        proxy_host = config.get("proxy_host", "").strip()
        proxy_port = int(config.get("proxy_port", 22))
        proxy_user = config.get("proxy_user", "root").strip()
        proxy_password = config.get("proxy_password", "")
        proxy_xui_user = config.get("proxy_xui_username", "").strip() or xui_username
        proxy_xui_pass = config.get("proxy_xui_password", "").strip() or xui_password
        proxy_secret = config.get("proxy_sub_secret", "").strip() or sub_secret
        proxy_xui_version = config.get("proxy_xui_version", "").strip() or xui_version
        
        proxy_tcp_raw = config.get("proxy_client_tcp_list", "").strip() or tcp_raw
        proxy_xhttp_raw = config.get("proxy_client_xhttp_list", "").strip() or xhttp_raw
        proxy_clients_tcp_str = " ".join([name.strip() for name in re.split(r'[\s,]+', proxy_tcp_raw) if name.strip()])
        proxy_clients_xhttp_str = " ".join([name.strip() for name in re.split(r'[\s,]+', proxy_xhttp_raw) if name.strip()])

        # Stage 1: Freedom Node
        log("=========================================", "info")
        log(f"[STAGE 1/2] Deploying foreign server (Freedom Node) on {freedom_host}...", "info")
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
        ok1, out1 = await _deploy_node(freedom_host, freedom_port, freedom_user, freedom_password, "", freedom_env, log)
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

        # Stage 2: Proxy Node
        log("=========================================", "info")
        log(f"[STAGE 2/2] Deploying local server (Proxy Node) on {proxy_host}...", "info")
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
        ok2, out2 = await _deploy_node(proxy_host, proxy_port, proxy_user, proxy_password, "", proxy_env, log)
        if not ok2:
            log("[ERROR] Stage 2 failed: Could not deploy local server.", "error")
            return False, {}
        parsed_xui_url, parsed_clients = parse_deployment_results(out2) if ok2 else ("", [])
        proxy_web_path = hashlib.md5(f"{proxy_secret}-panel".encode('utf-8')).hexdigest()[:16]
        final_xui_url = parsed_xui_url or f"https://{proxy_host}/{proxy_web_path}/"
        freedom_web_path = hashlib.md5(f"{freedom_secret}-panel".encode('utf-8')).hexdigest()[:16]
        freedom_final_xui_url = freedom_xui_url or f"https://{freedom_host}/{freedom_web_path}/"
        result_data = {
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
        log("=========================================", "success")
        log("🎉 CASCADE DEPLOYMENT COMPLETED SUCCESSFULLY!", "success")
        log(f"Panel 1 (Freedom Node): {freedom_final_xui_url}", "success")
        log(f"  - Admin User: {freedom_xui_user}", "success")
        log(f"  - Admin Password: ••••••••", "success")
        log(f"Panel 2 (Proxy Node): {final_xui_url}", "success")
        log(f"  - Admin User: {proxy_xui_user}", "success")
        log(f"  - Admin Password: ••••••••", "success")
        log(f"  - Subscription Path: ••••••••", "success")
        log("=========================================", "success")
        return True, result_data