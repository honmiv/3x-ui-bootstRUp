#!/usr/bin/env python3
"""Unit test for validate_deployment_config in single mode."""

import os
import sys
import unittest

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from ssh_deployer import validate_deployment_config


class TestValidateSingleMode(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
