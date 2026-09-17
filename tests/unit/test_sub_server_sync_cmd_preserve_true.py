#!/usr/bin/env python3
"""Unit test: _sub_server_sync_cmd with preserve=True generates state file backup/restore."""

import os
import sys
import unittest

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

import ssh_deployer


class TestSubServerSyncPreserveTrue(unittest.TestCase):
    def test_sync_cmd_with_preserve_true(self):
        cmd = ssh_deployer._sub_server_sync_cmd("/opt/3x-ui-bootstRUp", preserve=True)
        self.assertIn("mkdir -p /opt/3x-ui-bootstRUp", cmd)
        self.assertIn("tar -xzf - -C /opt/3x-ui-bootstRUp", cmd)
        self.assertIn("for f in subs.yml force-subs.yml nodes.json sub-server.log; do", cmd)
        self.assertIn("cp /opt/3x-ui-bootstRUp/sub-server/$f /tmp/sub-server-$f.bak", cmd)
        self.assertIn("cp /tmp/sub-server-$f.bak /opt/3x-ui-bootstRUp/sub-server/$f", cmd)
        self.assertIn("rm -f /tmp/sub-server-$f.bak", cmd)


if __name__ == "__main__":
    unittest.main()
