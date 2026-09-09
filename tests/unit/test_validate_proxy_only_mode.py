#!/usr/bin/env python3
"""Unit test for validate_deployment_config in proxy_only mode."""

import os
import sys
import unittest

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from ssh_deployer import validate_deployment_config


class TestValidateProxyOnlyMode(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
