#!/usr/bin/env python3
"""Unit test: extract_domain_from_url with standard HTTP and HTTPS URLs."""

import os
import sys
import unittest

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

import ssh_deployer


class TestExtractDomainStandardUrls(unittest.TestCase):
    def test_standard_urls(self):
        self.assertEqual(ssh_deployer.extract_domain_from_url("https://sub.example.com"), "sub.example.com")
        self.assertEqual(ssh_deployer.extract_domain_from_url("http://example.com/"), "example.com")
        self.assertEqual(ssh_deployer.extract_domain_from_url("http://example.com/sub/path"), "example.com")


if __name__ == "__main__":
    unittest.main()
