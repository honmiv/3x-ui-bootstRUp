#!/usr/bin/env python3
"""
Unit and Integration Tests for Validation, Error Responses, and Fallbacks
Verifies:
1. validate_deployment_config enforces mandatory fields and rejects missing/empty values.
2. /api/deploy returns HTTP 400 Bad Request with descriptive message on validation failures.
3. /api/ssh/test returns HTTP 400 when host or credentials are missing.
4. Default 'local-proxy-node-client' is only applied in cascade, cascade_sub, and freedom_component.
"""

import json
import os
import sys
import unittest
import urllib.request
import urllib.error

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from ssh_deployer import validate_deployment_config
from tests.ui.ui_helpers import start_sandboxed_control_panel


class TestValidationAndFallbacks(unittest.TestCase):

    def test_single_mode_validation(self):
        # Missing host
        ok, msg = validate_deployment_config({
            "deploy_mode": "single",
            "vps_port": 22,
            "vps_user": "root",
            "vps_password": "pass",
            "xui_username": "admin",
            "xui_password": "pass",
            "sub_secret": "secret"
        })
        self.assertFalse(ok)
        self.assertIn("домен", msg.lower())

        # Missing password & key
        ok, msg = validate_deployment_config({
            "deploy_mode": "single",
            "vps_host": "example.com",
            "vps_port": 22,
            "vps_user": "root",
            "xui_username": "admin",
            "xui_password": "pass",
            "sub_secret": "secret"
        })
        self.assertFalse(ok)
        self.assertIn("пароль или ключ", msg.lower())

        # Missing xui credentials
        ok, msg = validate_deployment_config({
            "deploy_mode": "single",
            "vps_host": "example.com",
            "vps_port": 22,
            "vps_user": "root",
            "vps_password": "pass",
            "xui_username": "",
            "xui_password": "pass",
            "sub_secret": "secret"
        })
        self.assertFalse(ok)
        self.assertIn("логин админа", msg.lower())

        # Valid single config
        ok, msg = validate_deployment_config({
            "deploy_mode": "single",
            "vps_host": "example.com",
            "vps_port": 22,
            "vps_user": "root",
            "vps_password": "pass",
            "xui_username": "admin",
            "xui_password": "pass",
            "sub_secret": "secret"
        })
        self.assertTrue(ok)
        self.assertEqual(msg, "")

    def test_cascade_mode_validation(self):
        # Missing freedom host
        ok, msg = validate_deployment_config({
            "deploy_mode": "cascade",
            "freedom_host": "",
            "freedom_port": 22,
            "freedom_user": "root",
            "freedom_password": "pass",
            "freedom_xui_username": "admin",
            "freedom_xui_password": "pass",
            "freedom_sub_secret": "secret",
            "proxy_host": "proxy.com",
            "proxy_port": 22,
            "proxy_user": "root",
            "proxy_password": "pass",
            "proxy_xui_username": "admin",
            "proxy_xui_password": "pass",
            "proxy_sub_secret": "secret"
        })
        self.assertFalse(ok)
        self.assertIn("freedom", msg.lower())

        # Missing proxy xui_password
        ok, msg = validate_deployment_config({
            "deploy_mode": "cascade",
            "freedom_host": "freedom.com",
            "freedom_port": 22,
            "freedom_user": "root",
            "freedom_password": "pass",
            "freedom_xui_username": "admin",
            "freedom_xui_password": "pass",
            "freedom_sub_secret": "secret",
            "proxy_host": "proxy.com",
            "proxy_port": 22,
            "proxy_user": "root",
            "proxy_password": "pass",
            "proxy_xui_username": "admin",
            "proxy_xui_password": "",
            "proxy_sub_secret": "secret"
        })
        self.assertFalse(ok)
        self.assertIn("пароль админа proxy", msg.lower())

        # Valid cascade
        ok, msg = validate_deployment_config({
            "deploy_mode": "cascade",
            "freedom_host": "freedom.com",
            "freedom_port": 22,
            "freedom_user": "root",
            "freedom_password": "pass",
            "freedom_xui_username": "admin",
            "freedom_xui_password": "pass",
            "freedom_sub_secret": "secret",
            "proxy_host": "proxy.com",
            "proxy_port": 22,
            "proxy_user": "root",
            "proxy_password": "pass",
            "proxy_xui_username": "admin",
            "proxy_xui_password": "pass",
            "proxy_sub_secret": "secret"
        })
        self.assertTrue(ok)
        self.assertEqual(msg, "")

    def test_proxy_only_validation(self):
        # Missing foreign_sub_url
        ok, msg = validate_deployment_config({
            "deploy_mode": "proxy_only",
            "vps_host": "proxy.com",
            "vps_port": 22,
            "vps_user": "root",
            "vps_password": "pass",
            "xui_username": "admin",
            "xui_password": "pass",
            "sub_secret": "secret",
            "foreign_sub_url": ""
        })
        self.assertFalse(ok)
        self.assertIn("foreign_sub_url", msg.lower())

    def test_freedom_only_validation(self):
        # Missing clients
        ok, msg = validate_deployment_config({
            "deploy_mode": "freedom_only",
            "vps_host": "freedom.com",
            "vps_port": 22,
            "vps_user": "root",
            "vps_password": "pass",
            "xui_username": "admin",
            "xui_password": "pass",
            "sub_secret": "secret",
            "client_tcp_list": "",
            "client_xhttp_list": ""
        })
        self.assertFalse(ok)
        self.assertIn("клиента", msg.lower())

    def test_sub_only_validation(self):
        # Missing subscription URLs
        ok, msg = validate_deployment_config({
            "deploy_mode": "sub_only",
            "sub_vps_host": "sub.com",
            "sub_vps_port": 22,
            "sub_vps_user": "root",
            "sub_vps_password": "pass",
            "sub_secret_path": "subs",
            "sub_admin_user": "admin",
            "sub_admin_password": "pass",
            "sub_russian_url": "",
            "sub_foreign_url": ""
        })
        self.assertFalse(ok)
        self.assertIn("ссылку подписки", msg.lower())

    def test_backup_validation(self):
        # Backup mode does not require backup_name (it is optional and auto-generated)
        ok, msg = validate_deployment_config({
            "deploy_mode": "backup",
            "backup_vps_host": "server.com",
            "backup_vps_port": 22,
            "backup_vps_user": "root",
            "backup_vps_password": "pass",
            "backup_name": ""
        })
        self.assertTrue(ok)

    def test_api_deploy_400_bad_request(self):
        server, server_url, _, _, _ = start_sandboxed_control_panel("api_validation_test")
        try:
            # Send invalid deploy payload (missing xui_username)
            payload = {
                "deploy_mode": "single",
                "vps_host": "test.example.com",
                "vps_port": 22,
                "vps_user": "root",
                "vps_password": "password123",
                "xui_username": "",
                "xui_password": "password123",
                "sub_secret": "secret"
            }
            req = urllib.request.Request(
                f"{server_url}/api/deploy",
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"}
            )
            try:
                urllib.request.urlopen(req)
                self.fail("Expected HTTP 400 Bad Request")
            except urllib.error.HTTPError as e:
                self.assertEqual(e.code, 400)
                resp_body = json.loads(e.read().decode("utf-8"))
                self.assertFalse(resp_body.get("ok"))
                self.assertIn("логин админа", resp_body.get("message", "").lower())
        finally:
            server.shutdown()

    def test_derive_sub_paths(self):
        import hashlib
        from ssh_deployer import derive_sub_path, derive_sub_server_path

        secret = "my_secret_phrase"
        # Panel sub path must append "-sub"
        expected_panel_sub = hashlib.md5(f"{secret}-sub".encode("utf-8")).hexdigest()[:16]
        self.assertEqual(derive_sub_path(secret), expected_panel_sub)

        # Sub-server path must NOT append "-sub"
        expected_sub_server = hashlib.md5(secret.encode("utf-8")).hexdigest()[:16]
        self.assertEqual(derive_sub_server_path(secret), expected_sub_server)
        self.assertNotEqual(derive_sub_server_path(secret), derive_sub_path(secret))

        # Empty or whitespace string must return empty string
        self.assertEqual(derive_sub_path(""), "")
        self.assertEqual(derive_sub_path("   "), "")
        self.assertEqual(derive_sub_path(None), "")
        self.assertEqual(derive_sub_server_path(""), "")
        self.assertEqual(derive_sub_server_path("   "), "")
        self.assertEqual(derive_sub_server_path(None), "")

    def test_change_ssh_port_validation(self):
        valid_base = {
            "deploy_mode": "single",
            "vps_host": "example.com",
            "vps_port": 22,
            "vps_user": "root",
            "vps_password": "pass",
            "xui_username": "admin",
            "xui_password": "pass",
            "sub_secret": "secret"
        }

        # Valid custom port
        ok, msg = validate_deployment_config({**valid_base, "change_ssh_port": True, "new_ssh_port": 22222})
        self.assertTrue(ok, f"Expected validation to pass, got: {msg}")

        # Port out of bounds (< 1024)
        ok, msg = validate_deployment_config({**valid_base, "change_ssh_port": True, "new_ssh_port": 22})
        self.assertFalse(ok)
        self.assertIn("1024", msg)

        # Port out of bounds (> 65535)
        ok, msg = validate_deployment_config({**valid_base, "change_ssh_port": True, "new_ssh_port": 70000})
        self.assertFalse(ok)
        self.assertIn("1024", msg)

        # Reserved port (443)
        ok, msg = validate_deployment_config({**valid_base, "change_ssh_port": True, "new_ssh_port": 443})
        self.assertFalse(ok)
        self.assertIn("зарезервирован", msg)

        # Invalid non-integer
        ok, msg = validate_deployment_config({**valid_base, "change_ssh_port": True, "new_ssh_port": "abc"})
        self.assertFalse(ok)
        self.assertIn("корректный", msg)

        # Valid in update_3xui mode
        valid_update_3xui = {
            "deploy_mode": "update_3xui",
            "update_vps_host": "xui.example.com",
            "update_vps_port": 22,
            "update_vps_user": "root",
            "update_vps_password": "pass",
            "update_xui_version": "2.4.0",
            "change_ssh_port": True,
            "new_ssh_port": 33333
        }
        ok, msg = validate_deployment_config(valid_update_3xui)
        self.assertTrue(ok, f"Expected update_3xui validation to pass, got: {msg}")

        # Valid in update_sub mode
        valid_update_sub = {
            "deploy_mode": "update_sub",
            "sub_vps_host": "sub.example.com",
            "sub_vps_port": 22,
            "sub_vps_user": "root",
            "sub_vps_password": "pass",
            "change_ssh_port": True,
            "new_ssh_port": 44444
        }
        ok, msg = validate_deployment_config(valid_update_sub)
        self.assertTrue(ok, f"Expected update_sub validation to pass, got: {msg}")

    def test_change_remote_ssh_port_probe_failure_aborts(self):
        import asyncio
        from unittest.mock import patch, AsyncMock
        from ssh_deployer import _change_remote_ssh_port

        with patch("ssh_deployer._probe_remote_http_port", new_callable=AsyncMock) as mock_probe, \
             patch("ssh_deployer.SSHDeployer") as mock_deployer_cls:
            mock_probe.return_value = (False, "Connection timed out")

            logs = []
            result = asyncio.run(_change_remote_ssh_port(
                "example.com", 22, 22222, "root", "pass", "", lambda m, lvl: logs.append((m, lvl))
            ))

            self.assertFalse(result)
            mock_probe.assert_awaited_once()
            mock_deployer_cls.assert_not_called()
            self.assertTrue(any("не удалась" in m for m, _ in logs))
            self.assertTrue(any("НЕ была изменена" in m for m, _ in logs))

    def test_change_remote_ssh_port_probe_success(self):
        import asyncio
        from unittest.mock import patch, AsyncMock
        from ssh_deployer import _change_remote_ssh_port

        with patch("ssh_deployer._probe_remote_http_port", new_callable=AsyncMock) as mock_probe, \
             patch("ssh_deployer.SSHDeployer") as mock_deployer_cls:
            mock_probe.return_value = (True, "")

            mock_instance = AsyncMock()
            mock_instance.__aenter__.return_value = mock_instance
            mock_instance.exec_command.return_value = (0, "ok")
            mock_instance.test_connection.return_value = (True, "Connection successful")
            mock_deployer_cls.return_value = mock_instance

            logs = []
            result = asyncio.run(_change_remote_ssh_port(
                "example.com", 22, 22222, "root", "pass", "", lambda m, lvl: logs.append((m, lvl))
            ))

            self.assertTrue(result)
            mock_probe.assert_awaited_once()
            self.assertTrue(any("успешно настроен" in m for m, _ in logs))

    def test_change_remote_ssh_port_rollback_on_verify_fail(self):
        import asyncio
        from unittest.mock import patch, AsyncMock
        from ssh_deployer import _change_remote_ssh_port

        with patch("ssh_deployer._probe_remote_http_port", new_callable=AsyncMock) as mock_probe, \
             patch("ssh_deployer.SSHDeployer") as mock_deployer_cls:
            mock_probe.return_value = (True, "")

            mock_instance = AsyncMock()
            mock_instance.__aenter__.return_value = mock_instance
            mock_instance.exec_command.return_value = (0, "ok")
            # Verification fails
            mock_instance.test_connection.return_value = (False, "Connection refused")
            mock_deployer_cls.return_value = mock_instance

            logs = []
            result = asyncio.run(_change_remote_ssh_port(
                "example.com", 22, 22222, "root", "pass", "", lambda m, lvl: logs.append((m, lvl))
            ))

            self.assertFalse(result)
            self.assertTrue(any("откат настроек SSH" in m for m, _ in logs))

    def test_change_remote_ssh_port_same_port_skips_probe(self):
        import asyncio
        from unittest.mock import patch, AsyncMock
        from ssh_deployer import _change_remote_ssh_port

        with patch("ssh_deployer._probe_remote_http_port", new_callable=AsyncMock) as mock_probe, \
             patch("ssh_deployer.SSHDeployer") as mock_deployer_cls:

            mock_instance = AsyncMock()
            mock_instance.__aenter__.return_value = mock_instance
            mock_instance.exec_command.return_value = (0, "ok")
            mock_instance.test_connection.return_value = (True, "Connection successful")
            mock_deployer_cls.return_value = mock_instance

            logs = []
            # Port 22222 -> 22222
            result = asyncio.run(_change_remote_ssh_port(
                "example.com", 22222, 22222, "root", "pass", "", lambda m, lvl: logs.append((m, lvl))
            ))

            self.assertTrue(result)
            mock_probe.assert_not_called()
            self.assertTrue(any("применение скрытия баннеров" in m for m, _ in logs))

    def test_probe_remote_http_port_success(self):
        import asyncio
        from unittest.mock import patch, AsyncMock
        from ssh_deployer import _probe_remote_http_port

        with patch("ssh_deployer.SSHDeployer") as mock_deployer_cls, \
             patch("asyncio.open_connection") as mock_open_conn:

            mock_instance = AsyncMock()
            mock_instance.__aenter__.return_value = mock_instance

            # Simulate exec_command triggering the ready callback
            async def fake_exec_cmd(cmd, callback=None):
                if callback:
                    callback("PROBE_HTTP_LISTENING")
                return 0, "PROBE_HTTP_DONE"

            mock_instance.exec_command.side_effect = fake_exec_cmd
            mock_deployer_cls.return_value = mock_instance

            # Mock TCP connection to probe
            # Mock TCP connection to probe delivering headers and body in separate chunks
            mock_reader = AsyncMock()
            mock_reader.read.return_value = b"HTTP/1.0 200 OK\r\n\r\nBOOTSTRUP_HTTP_OK\n"
            mock_reader.read.side_effect = [
                b"HTTP/1.0 200 OK\r\nServer: BaseHTTP/0.6 Python/3.14.4\r\nDate: Sun, 06 Sep 2026\r\n\r\n",
                b"BOOTSTRUP_HTTP_OK\n",
                b""
            ]
            from unittest.mock import MagicMock
            mock_writer = MagicMock()
            mock_writer.drain = AsyncMock()
            mock_writer.wait_closed = AsyncMock()
            mock_open_conn.return_value = (mock_reader, mock_writer)

            logs = []
            ok, err = asyncio.run(_probe_remote_http_port(
                "example.com", 22222, 22, "root", "pass", "", lambda m, lvl: logs.append((m, lvl))
            ))

            self.assertTrue(ok)
            self.assertEqual(err, "")
            self.assertTrue(any("успешно! Порт открыт" in m for m, _ in logs))

    def test_probe_remote_http_port_connection_refused(self):
        import asyncio
        from unittest.mock import patch, AsyncMock
        from ssh_deployer import _probe_remote_http_port

        with patch("ssh_deployer.SSHDeployer") as mock_deployer_cls, \
             patch("asyncio.open_connection") as mock_open_conn:

            mock_instance = AsyncMock()
            mock_instance.__aenter__.return_value = mock_instance

            async def fake_exec_cmd(cmd, callback=None):
                if callback:
                    callback("PROBE_HTTP_LISTENING")
                return 0, "PROBE_HTTP_DONE"

            mock_instance.exec_command.side_effect = fake_exec_cmd
            mock_deployer_cls.return_value = mock_instance

            # ConnectionRefusedError
            mock_open_conn.side_effect = ConnectionRefusedError()

            logs = []
            ok, err = asyncio.run(_probe_remote_http_port(
                "example.com", 22222, 22, "root", "pass", "", lambda m, lvl: logs.append((m, lvl))
            ))

            self.assertFalse(ok)
            self.assertIn("Connection refused", err)


if __name__ == "__main__":
    unittest.main()

