#!/usr/bin/env python3
"""Unit test: extract_domain_from_url strips custom ports."""

import os
import sys
import unittest

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

import ssh_deployer


class TestExtractDomainUrlsWithPorts(unittest.TestCase):
    def test_urls_with_ports(self):
        self.assertEqual(ssh_deployer.extract_domain_from_url("https://example.com:8443"), "example.com")
        self.assertEqual(ssh_deployer.extract_domain_from_url("http://node.test.org:2053/panel"), "node.test.org")


if __name__ == "__main__":
    unittest.main()
