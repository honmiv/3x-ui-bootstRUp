#!/usr/bin/env python3
"""Unit test for custom SSH port validation across modes."""

import os
import sys
import unittest

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from ssh_deployer import validate_deployment_config


class TestChangeSshPortValidation(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
