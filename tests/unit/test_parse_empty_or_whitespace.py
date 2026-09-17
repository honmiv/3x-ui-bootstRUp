#!/usr/bin/env python3
"""Unit test: parse_deployment_results handles empty or whitespace input."""

import os
import sys
import unittest

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

import ssh_deployer


class TestParseEmptyOrWhitespace(unittest.TestCase):
    def test_empty_or_whitespace_output(self):
        self.assertEqual(ssh_deployer.parse_deployment_results(""), ("", []))
        self.assertEqual(ssh_deployer.parse_deployment_results("   \n\t  \n"), ("", []))


if __name__ == "__main__":
    unittest.main()
