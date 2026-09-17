#!/usr/bin/env python3
"""Unit test for ServerConnection.validate port boundary checking."""

import os
import sys
import unittest

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from ssh_deployer import ServerConnection


class TestServerConnValidatePortBoundaries(unittest.TestCase):
    def test_validate_port_boundaries(self):
        label = "тестового сервера"
        # Port string "0" -> error
        conn = ServerConnection(host="1.2.3.4", port="0", user="root", password="p", key_data="")
        self.assertIn("корректный SSH порт", conn.validate(label))

        # Port negative -> error
        conn = ServerConnection(host="1.2.3.4", port=-1, user="root", password="p", key_data="")
        self.assertIn("корректный SSH порт", conn.validate(label))

        # Port > 65535 -> error
        conn = ServerConnection(host="1.2.3.4", port=65536, user="root", password="p", key_data="")
        self.assertIn("корректный SSH порт", conn.validate(label))

        # Invalid string port -> error
        conn = ServerConnection(host="1.2.3.4", port="invalid_port", user="root", password="p", key_data="")
        self.assertIn("корректный SSH порт", conn.validate(label))

        # Valid lower and upper bounds
        conn = ServerConnection(host="1.2.3.4", port=1, user="root", password="p", key_data="")
        self.assertIsNone(conn.validate(label))

        conn = ServerConnection(host="1.2.3.4", port=65535, user="root", password="p", key_data="")
        self.assertIsNone(conn.validate(label))

        # None or empty string port defaults to 22 (valid)
        conn = ServerConnection(host="1.2.3.4", port=None, user="root", password="p", key_data="")
        self.assertIsNone(conn.validate(label))

        conn = ServerConnection(host="1.2.3.4", port="", user="root", password="p", key_data="")
        self.assertIsNone(conn.validate(label))


if __name__ == "__main__":
    unittest.main()
