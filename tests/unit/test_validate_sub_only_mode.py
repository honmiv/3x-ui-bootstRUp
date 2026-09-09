#!/usr/bin/env python3
"""Unit test for validate_deployment_config in sub_only mode."""

import os
import sys
import unittest

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from ssh_deployer import validate_deployment_config


class TestValidateSubOnlyMode(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
