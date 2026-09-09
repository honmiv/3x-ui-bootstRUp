#!/usr/bin/env python3
"""Signature test for ssh_deployer.run_deployment."""

import inspect
import os
import sys
import unittest

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

import ssh_deployer


class TestSigRunDeployment(unittest.TestCase):
    def test_ssh_deployer_run_deployment_signature(self):
        sig = inspect.signature(ssh_deployer.run_deployment)
        params = list(sig.parameters.values())
        self.assertEqual([p.name for p in params], ["config", "log_callback", "cancel_check"])
        self.assertIsNot(params[2].default, inspect.Parameter.empty)
        self.assertIsNone(params[2].default)


if __name__ == "__main__":
    unittest.main()
