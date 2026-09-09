#!/usr/bin/env python3
"""Unit test for ServerConnection.validate with various auth credentials."""

import os
import sys
import unittest

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from ssh_deployer import ServerConnection


class TestServerConnValidateAuthCredentials(unittest.TestCase):
    def test_validate_auth_credentials(self):
        label = "VPS сервера"
        # Neither password nor key -> error
        conn = ServerConnection(host="1.2.3.4", port=22, user="root", password="", key_data="")
        err = conn.validate(label)
        self.assertIsNotNone(err)
        self.assertIn("пароль или ключ VPS сервера", err)

        # Password only -> valid
        conn_pass = ServerConnection(host="1.2.3.4", port=22, user="root", password="my_password", key_data="")
        self.assertIsNone(conn_pass.validate(label))

        # Key only -> valid
        conn_key = ServerConnection(host="1.2.3.4", port=22, user="root", password="", key_data="KEY_DATA")
        self.assertIsNone(conn_key.validate(label))

        # Both password and key -> valid
        conn_both = ServerConnection(host="1.2.3.4", port=22, user="root", password="p", key_data="k")
        self.assertIsNone(conn_both.validate(label))


if __name__ == "__main__":
    unittest.main()
