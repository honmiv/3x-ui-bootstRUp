#!/usr/bin/env python3
"""Unit test for validate_deployment_config in rollback_sub mode."""

import os
import sys
import unittest

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from ssh_deployer import validate_deployment_config


class TestValidateRollbackSub(unittest.TestCase):
    def test_rollback_sub_validation(self):
        base_rollback = {
            "deploy_mode": "rollback_sub",
            "sub_vps_host": "sub.com",
            "sub_vps_port": 22,
            "sub_vps_user": "root",
            "sub_vps_password": "pass",
        }

        # Missing rollback backup archive
        ok, msg = validate_deployment_config({**base_rollback, "rollback_sub_backup_file": ""})
        self.assertFalse(ok)
        self.assertIn("архив бэкапа сервера подписок", msg.lower())

        # Valid rollback_sub
        ok, msg = validate_deployment_config({**base_rollback, "rollback_sub_backup_file": "sub_backup_2026.tar.gz"})
        self.assertTrue(ok)
        self.assertEqual(msg, "")


if __name__ == "__main__":
    unittest.main()
