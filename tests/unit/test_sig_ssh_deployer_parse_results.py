#!/usr/bin/env python3
"""Signature test for ssh_deployer.parse_deployment_results."""

import inspect
import os
import sys
import unittest

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

import ssh_deployer


class TestSigParseResults(unittest.TestCase):
    def test_ssh_deployer_parse_deployment_results_signature(self):
        sig = inspect.signature(ssh_deployer.parse_deployment_results)
        self.assertEqual(list(sig.parameters.keys()), ["output_text"])


if __name__ == "__main__":
    unittest.main()
