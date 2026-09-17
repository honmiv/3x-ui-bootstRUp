#!/usr/bin/env python3
"""Unit test: parse_deployment_results handles corrupted JSON between markers."""

import os
import sys
import unittest

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

import ssh_deployer


class TestParseCorruptedJson(unittest.TestCase):
    def test_corrupted_json_between_markers(self):
        corrupted = """
        ===RESULT_JSON_START===
        { this is not valid json : [ }
        ===RESULT_JSON_END===
        """
        self.assertEqual(ssh_deployer.parse_deployment_results(corrupted), ("", []))


if __name__ == "__main__":
    unittest.main()
