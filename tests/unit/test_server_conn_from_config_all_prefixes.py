#!/usr/bin/env python3
"""Unit test for ServerConnection.from_config across all 7 server prefixes."""

import os
import sys
import unittest

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from ssh_deployer import ServerConnection


class TestServerConnFromConfigPrefixes(unittest.TestCase):
    PREFIXES = [
        "vps", "freedom", "proxy", "sub_vps",
        "backup_vps", "recovery_vps", "update_vps",
    ]

    def test_from_config_all_prefixes(self):
        for prefix in self.PREFIXES:
            config = {
                f"{prefix}_host": "  1.2.3.4  ",
                f"{prefix}_port": 2222,
                f"{prefix}_user": "  deploy_user  ",
                f"{prefix}_password": "secret_password",
                f"{prefix}_key": "-----BEGIN OPENSSH PRIVATE KEY-----...",
            }
            conn = ServerConnection.from_config(config, prefix)
            self.assertEqual(conn.host, "1.2.3.4")
            self.assertEqual(conn.port, 2222)
            self.assertEqual(conn.user, "deploy_user")
            self.assertEqual(conn.password, "secret_password")
            self.assertEqual(conn.key_data, "-----BEGIN OPENSSH PRIVATE KEY-----...")


if __name__ == "__main__":
    unittest.main()
