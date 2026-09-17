#!/usr/bin/env python3
"""Unit test for ServerConnection.from_config default and None handling."""

import os
import sys
import unittest

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from ssh_deployer import ServerConnection


class TestServerConnFromConfigDefaults(unittest.TestCase):
    def test_from_config_defaults_and_none(self):
        conn = ServerConnection.from_config({}, "vps")
        self.assertEqual(conn.host, "")
        self.assertIsNone(conn.port)
        self.assertEqual(conn.user, "")
        self.assertEqual(conn.password, "")
        self.assertEqual(conn.key_data, "")

        conn_none = ServerConnection.from_config(
            {"vps_host": None, "vps_port": None, "vps_user": None, "vps_password": None, "vps_key": None},
            "vps",
        )
        self.assertEqual(conn_none.host, "")
        self.assertIsNone(conn_none.port)
        self.assertEqual(conn_none.user, "")
        self.assertEqual(conn_none.password, "")
        self.assertEqual(conn_none.key_data, "")


if __name__ == "__main__":
    unittest.main()
