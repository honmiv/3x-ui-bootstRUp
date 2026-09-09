#!/usr/bin/env python3
"""Unit test for validate_deployment_config in cascade mode."""

import os
import sys
import unittest

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from ssh_deployer import validate_deployment_config


class TestValidateCascadeMode(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
