#!/usr/bin/env python3
"""Signature test for ssh_deployer._sub_server_sync_cmd."""

import inspect
import os
import sys
import unittest

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

import ssh_deployer


class TestSigSubServerSyncCmd(unittest.TestCase):
    def test_ssh_deployer_sub_server_sync_cmd_signature(self):
        sig = inspect.signature(ssh_deployer._sub_server_sync_cmd)
        self.assertEqual(list(sig.parameters.keys()), ["remote_dir", "preserve"])


if __name__ == "__main__":
    unittest.main()
