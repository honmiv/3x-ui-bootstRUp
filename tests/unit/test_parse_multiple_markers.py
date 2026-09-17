#!/usr/bin/env python3
"""Unit test: parse_deployment_results uses the first result block when multiple exist."""

import os
import sys
import unittest

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

import ssh_deployer


class TestParseMultipleMarkers(unittest.TestCase):
    def test_multiple_markers_uses_first_block(self):
        multiple = """
        ===RESULT_JSON_START===
        {"panel_url": "http://first.com", "clients": [{"name": "client1"}]}
        ===RESULT_JSON_END===
        Some intermediate logs
        ===RESULT_JSON_START===
        {"panel_url": "http://second.com", "clients": [{"name": "client2"}]}
        ===RESULT_JSON_END===
        """
        panel_url, clients = ssh_deployer.parse_deployment_results(multiple)
        self.assertEqual(panel_url, "http://first.com")
        self.assertEqual(len(clients), 1)
        self.assertEqual(clients[0]["name"], "client1")


if __name__ == "__main__":
    unittest.main()
