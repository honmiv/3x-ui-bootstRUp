#!/usr/bin/env python3
"""Unit test: parse_deployment_results ignores ANSI color codes in surrounding logs."""

import os
import sys
import unittest

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

import ssh_deployer


class TestParseAnsiAndControlChars(unittest.TestCase):
    def test_robustness_with_ansi_codes_and_control_chars(self):
        ansi_output = """
        \x1b[32m[OK]\x1b[0m Starting service...
        ===RESULT_JSON_START===
        {
            "panel_url": "http://clean.domain.com",
            "clients": [{"name": "safe_client", "sub_url": "http://clean.domain.com/sub"}]
        }
        ===RESULT_JSON_END===
        \x1b[31m[DONE]\x1b[0m
        """
        panel_url, clients = ssh_deployer.parse_deployment_results(ansi_output)
        self.assertEqual(panel_url, "http://clean.domain.com")
        self.assertEqual(len(clients), 1)
        self.assertEqual(clients[0]["name"], "safe_client")


if __name__ == "__main__":
    unittest.main()
