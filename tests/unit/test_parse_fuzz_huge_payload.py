#!/usr/bin/env python3
"""Fuzz test: parse_deployment_results handles large log and client payloads."""

import json
import os
import sys
import unittest

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

import ssh_deployer


class TestParseFuzzHugePayload(unittest.TestCase):
    def test_fuzz_huge_payload(self):
        huge_log = "[LOG] " + ("A" * 100000) + "\n"
        huge_payload = {
            "panel_url": "https://example.com/" + ("x" * 1000),
            "clients": [{"name": f"client_{i}", "sub_url": "http://test"} for i in range(200)]
        }
        full_text = (
            huge_log +
            "===RESULT_JSON_START===\n" +
            json.dumps(huge_payload) + "\n" +
            "===RESULT_JSON_END===\n" +
            huge_log
        )
        url, clients = ssh_deployer.parse_deployment_results(full_text)
        self.assertTrue(url.startswith("https://example.com/x"))
        self.assertEqual(len(clients), 200)


if __name__ == "__main__":
    unittest.main()
