#!/usr/bin/env python3
"""Unit test for validate_deployment_config in restart_panel and restart_server modes."""

import os
import sys
import unittest

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from ssh_deployer import validate_deployment_config


class TestValidateRestartModes(unittest.TestCase):
    def test_restart_modes_validation(self):
        for r_mode in ["restart_panel", "restart_server"]:
            # Missing host
            ok, msg = validate_deployment_config({
                "deploy_mode": r_mode,
                "update_vps_host": "",
                "update_vps_user": "root",
                "update_vps_password": "pass",
            })
            self.assertFalse(ok)
            self.assertIn("домен", msg.lower())

            # Valid without update_xui_version (restart does not require new version)
            ok, msg = validate_deployment_config({
                "deploy_mode": r_mode,
                "update_vps_host": "server.example.com",
                "update_vps_port": 22,
                "update_vps_user": "root",
                "update_vps_password": "pass",
            })
            self.assertTrue(ok)
            self.assertEqual(msg, "")


if __name__ == "__main__":
    unittest.main()
