"""Low-level async SSH/SCP transport (Phase C5 of REFACTORING.md).

Extracted from ssh_deployer.py::SSHDeployer. Shells out to the system
`ssh`/`scp` binaries; password auth via SSH_ASKPASS, optional private key.
"""

import asyncio
import os
import re
import sys
import tempfile
from typing import Callable, Optional

ANSI_ESCAPE = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')

def strip_ansi(text: str) -> str:
    return ANSI_ESCAPE.sub('', text)

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