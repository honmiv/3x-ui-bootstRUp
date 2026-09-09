#!/usr/bin/env python3
"""Unit test for ServerConnection.validate with missing user."""

import os
import sys
import unittest

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from ssh_deployer import ServerConnection


class TestServerConnValidateMissingUser(unittest.TestCase):
    def test_validate_missing_user(self):
        conn = ServerConnection(host="1.2.3.4", port=22, user="", password="p", key_data="")
        err = conn.validate("VPS сервера")
        self.assertIsNotNone(err)
        self.assertIn("SSH пользователя VPS сервера", err)


if __name__ == "__main__":
    unittest.main()
