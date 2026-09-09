#!/usr/bin/env python3
"""Unit test for ServerConnection.validate with missing host."""

import os
import sys
import unittest

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from ssh_deployer import ServerConnection


class TestServerConnValidateMissingHost(unittest.TestCase):
    def test_validate_missing_host(self):
        conn = ServerConnection(host="", port=22, user="root", password="pass", key_data="")
        err = conn.validate("VPS сервера")
        self.assertIsNotNone(err)
        self.assertIn("домен VPS сервера", err)


if __name__ == "__main__":
    unittest.main()
