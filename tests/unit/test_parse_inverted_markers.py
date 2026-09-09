#!/usr/bin/env python3
"""Unit test: parse_deployment_results handles inverted marker order."""

import os
import sys
import unittest

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

import ssh_deployer


class TestParseInvertedMarkers(unittest.TestCase):
    def test_inverted_markers(self):
        inverted = '===RESULT_JSON_END===\n{"panel_url": "http://test"}\n===RESULT_JSON_START==='
        self.assertEqual(ssh_deployer.parse_deployment_results(inverted), ("", []))


if __name__ == "__main__":
    unittest.main()
