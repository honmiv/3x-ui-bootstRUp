#!/usr/bin/env python3
"""Signature test for ssh_deployer sub path derivation functions."""

import inspect
import os
import sys
import unittest

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

import ssh_deployer


class TestSigDeriveSubPaths(unittest.TestCase):
    def test_ssh_deployer_derive_sub_paths_signature(self):
        self.assertEqual(list(inspect.signature(ssh_deployer.derive_sub_path).parameters.keys()), ["secret"])
        self.assertEqual(list(inspect.signature(ssh_deployer.derive_sub_server_path).parameters.keys()), ["secret"])


if __name__ == "__main__":
    unittest.main()
