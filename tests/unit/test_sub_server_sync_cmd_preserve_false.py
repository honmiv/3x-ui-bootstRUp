#!/usr/bin/env python3
"""Unit test: _sub_server_sync_cmd with preserve=False does not create state backups."""

import os
import sys
import unittest

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

import ssh_deployer


class TestSubServerSyncPreserveFalse(unittest.TestCase):
    def test_sync_cmd_with_preserve_false(self):
        cmd = ssh_deployer._sub_server_sync_cmd("/custom/path", preserve=False)
        self.assertIn("mkdir -p /custom/path", cmd)
        self.assertIn("tar -xzf - -C /custom/path", cmd)
        self.assertNotIn("sub-server-$f.bak", cmd)
        self.assertIn("mkdir -p /custom/path && true && tar -xzf - -C /custom/path && true", cmd)


if __name__ == "__main__":
    unittest.main()
