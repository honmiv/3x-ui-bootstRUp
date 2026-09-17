#!/usr/bin/env python3
"""Unit test for validate_deployment_config in backup mode."""

import os
import sys
import unittest

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from ssh_deployer import validate_deployment_config


class TestValidateBackupMode(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
