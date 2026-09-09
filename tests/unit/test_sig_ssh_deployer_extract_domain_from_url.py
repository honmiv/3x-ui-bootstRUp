#!/usr/bin/env python3
"""Signature test for ssh_deployer.extract_domain_from_url."""

import inspect
import os
import sys
import unittest

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

import ssh_deployer


class TestSigExtractDomain(unittest.TestCase):
    def test_ssh_deployer_extract_domain_from_url_signature(self):
        sig = inspect.signature(ssh_deployer.extract_domain_from_url)
        self.assertEqual(list(sig.parameters.keys()), ["url"])


if __name__ == "__main__":
    unittest.main()
