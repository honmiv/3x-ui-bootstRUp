#!/usr/bin/env python3
"""Unit test: extract_domain_from_url handles empty and None inputs."""

import os
import sys
import unittest

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

import ssh_deployer


class TestExtractDomainEmptyWhitespace(unittest.TestCase):
    def test_empty_and_whitespace(self):
        self.assertEqual(ssh_deployer.extract_domain_from_url(""), "")
        self.assertEqual(ssh_deployer.extract_domain_from_url("   "), "")
        self.assertEqual(ssh_deployer.extract_domain_from_url(None), "")


if __name__ == "__main__":
    unittest.main()
