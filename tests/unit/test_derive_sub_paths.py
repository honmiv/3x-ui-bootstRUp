#!/usr/bin/env python3
"""Unit test for derive_sub_path and derive_sub_server_path hashing logic."""

import hashlib
import os
import sys
import unittest

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from ssh_deployer import derive_sub_path, derive_sub_server_path


class TestDeriveSubPaths(unittest.TestCase):
    def test_derive_sub_paths(self):
        secret = "my_secret_phrase"
        # Panel sub path must append "-sub"
        expected_panel_sub = hashlib.md5(f"{secret}-sub".encode("utf-8")).hexdigest()[:16]
        self.assertEqual(derive_sub_path(secret), expected_panel_sub)

        # Sub-server path must NOT append "-sub"
        expected_sub_server = hashlib.md5(secret.encode("utf-8")).hexdigest()[:16]
        self.assertEqual(derive_sub_server_path(secret), expected_sub_server)
        self.assertNotEqual(derive_sub_server_path(secret), derive_sub_path(secret))

        # Empty or whitespace string must return empty string
        self.assertEqual(derive_sub_path(""), "")
        self.assertEqual(derive_sub_path("   "), "")
        self.assertEqual(derive_sub_path(None), "")
        self.assertEqual(derive_sub_server_path(""), "")
        self.assertEqual(derive_sub_server_path("   "), "")
        self.assertEqual(derive_sub_server_path(None), "")


if __name__ == "__main__":
    unittest.main()
