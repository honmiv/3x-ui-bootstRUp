#!/usr/bin/env python3
"""Unit test for validate_deployment_config in freedom_component mode."""

import os
import sys
import unittest

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from ssh_deployer import validate_deployment_config


class TestValidateFreedomComponent(unittest.TestCase):
    def test_freedom_component_validation(self):
        # Missing sub_secret
        invalid_cfg = {
            "deploy_mode": "freedom_component",
            "vps_host": "freedom.example.com",
            "vps_port": 22,
            "vps_user": "root",
            "vps_password": "pass",
            "xui_username": "admin",
            "xui_password": "pass",
            "sub_secret": "",
        }
        ok, msg = validate_deployment_config(invalid_cfg)
        self.assertFalse(ok)
        self.assertIn("секретную фразу", msg.lower())

        # Valid freedom_component
        valid_cfg = {**invalid_cfg, "sub_secret": "my_secret"}
        ok, msg = validate_deployment_config(valid_cfg)
        self.assertTrue(ok)
        self.assertEqual(msg, "")


if __name__ == "__main__":
    unittest.main()
