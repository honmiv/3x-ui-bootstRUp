#!/usr/bin/env python3
"""Unit test for validate_deployment_config in freedom_only mode."""

import os
import sys
import unittest

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from ssh_deployer import validate_deployment_config


class TestValidateFreedomOnlyMode(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
