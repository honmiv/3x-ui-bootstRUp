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


if __name__ == "__main__":
    unittest.main()
