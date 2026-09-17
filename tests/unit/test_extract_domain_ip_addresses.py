#!/usr/bin/env python3
"""Unit test: extract_domain_from_url handles IP addresses."""

import os
import sys
import unittest

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

import ssh_deployer


class TestExtractDomainIpAddresses(unittest.TestCase):
    def test_ip_addresses(self):
        self.assertEqual(ssh_deployer.extract_domain_from_url("http://192.168.1.50"), "192.168.1.50")
        self.assertEqual(ssh_deployer.extract_domain_from_url("https://10.0.0.1:8000/api"), "10.0.0.1")


if __name__ == "__main__":
    unittest.main()
