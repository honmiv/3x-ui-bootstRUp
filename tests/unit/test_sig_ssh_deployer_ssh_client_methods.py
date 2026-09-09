#!/usr/bin/env python3
"""Signature test for SSHDeployer class core methods."""

import os
import sys
import unittest

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

import ssh_deployer


class TestSigSshClientMethods(unittest.TestCase):
    def test_ssh_deployer_ssh_client_methods(self):
        self.assertTrue(hasattr(ssh_deployer.SSHDeployer, "exec_command"))
        self.assertTrue(hasattr(ssh_deployer.SSHDeployer, "download_file"))
        self.assertTrue(hasattr(ssh_deployer.SSHDeployer, "test_connection"))


if __name__ == "__main__":
    unittest.main()
