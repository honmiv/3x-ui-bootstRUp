#!/usr/bin/env python3
"""Unit test: extract_domain_from_url with custom schemes and schemeless URLs."""

import os
import sys
import unittest

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

import ssh_deployer


class TestExtractDomainCustomSchemes(unittest.TestCase):
    def test_custom_schemes_and_no_scheme(self):
        self.assertEqual(ssh_deployer.extract_domain_from_url("vless://user@domain.com:443"), "user@domain.com")
        self.assertEqual(ssh_deployer.extract_domain_from_url("naked-domain.com/path"), "naked-domain.com")


if __name__ == "__main__":
    unittest.main()
