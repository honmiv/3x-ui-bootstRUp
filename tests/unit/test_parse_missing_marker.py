#!/usr/bin/env python3
"""Unit test: parse_deployment_results handles missing start or end marker."""

import os
import sys
import unittest

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

import ssh_deployer


class TestParseMissingMarker(unittest.TestCase):
    def test_missing_start_or_end_marker(self):
        no_end = '===RESULT_JSON_START===\n{"panel_url": "http://test"}'
        no_start = '{"panel_url": "http://test"}\n===RESULT_JSON_END==='
        self.assertEqual(ssh_deployer.parse_deployment_results(no_end), ("", []))
        self.assertEqual(ssh_deployer.parse_deployment_results(no_start), ("", []))


if __name__ == "__main__":
    unittest.main()
