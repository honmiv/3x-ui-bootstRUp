#!/usr/bin/env python3
"""Unit test for validate_deployment_config in cascade_sub mode."""

import os
import sys
import unittest

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from ssh_deployer import validate_deployment_config


class TestValidateCascadeSub(unittest.TestCase):
    def test_cascade_sub_validation(self):
        base_cascade = {
            "deploy_mode": "cascade_sub",
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
            "proxy_sub_secret": "secret",
        }

        # Missing Sub-server host
        ok, msg = validate_deployment_config({**base_cascade, "sub_vps_host": ""})
        self.assertFalse(ok)
        self.assertIn("сервера подписок", msg.lower())

        # Missing Sub-server password or key
        ok, msg = validate_deployment_config({
            **base_cascade,
            "sub_vps_host": "sub.com",
            "sub_vps_port": 22,
            "sub_vps_user": "root",
            "sub_vps_password": "",
            "sub_vps_key": "",
        })
        self.assertFalse(ok)
        self.assertIn("пароль или ключ", msg.lower())

        # Valid cascade_sub
        ok, msg = validate_deployment_config({
            **base_cascade,
            "sub_vps_host": "sub.com",
            "sub_vps_port": 22,
            "sub_vps_user": "root",
            "sub_vps_password": "sub_pass",
            "sub_secret_path": "my_subs",
            "sub_admin_user": "admin",
            "sub_admin_password": "pass",
        })
        self.assertTrue(ok)
        self.assertEqual(msg, "")


if __name__ == "__main__":
    unittest.main()
