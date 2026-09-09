#!/usr/bin/env python3
"""Fuzz test: parse_deployment_results handles abnormal types for url and clients gracefully."""

import os
import sys
import unittest

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

import ssh_deployer


class TestParseFuzzMalformedTypes(unittest.TestCase):
    def test_fuzz_malformed_client_types(self):
        test_payloads = [
            '{"panel_url": 12345, "clients": null}',
            '{"panel_url": null, "clients": ["not-a-dict", 42, null, true, []]}',
            '{"panel_url": "http://test", "clients": "string_instead_of_list"}',
            '{"panel_url": "http://test", "clients": [{"name": null, "sub_url": null}]}',
            '{"unexpected_key": {"deep": [1, 2, 3]}}',
        ]
        for payload in test_payloads:
            text = f"===RESULT_JSON_START===\n{payload}\n===RESULT_JSON_END==="
            try:
                url, clients = ssh_deployer.parse_deployment_results(text)
                self.assertIsInstance(url, (str, int))
                self.assertIsInstance(clients, list)
            except Exception as e:
                self.fail(f"parse_deployment_results raised {type(e).__name__}: {e} for payload: {payload}")


if __name__ == "__main__":
    unittest.main()
