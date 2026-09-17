#!/usr/bin/env python3
"""Unit test: parse_deployment_results handles unicode and query parameters."""

import os
import sys
import unittest

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

import ssh_deployer


class TestParseUnicodeAndSpecialChars(unittest.TestCase):
    def test_unicode_and_special_chars(self):
        sample_output = """
        ===RESULT_JSON_START===
        {
            "panel_url": "https://domain.com/path",
            "clients": [
                {
                    "name": "Иван Иванов 🚀",
                    "sub_url": "https://domain.com/sub/ivan?flag=1&test=true#hash",
                    "tcp_url": "vless://uuid@domain.com:443?security=reality&fp=chrome#Иван",
                    "xhttp_url": ""
                }
            ]
        }
        ===RESULT_JSON_END===
        """
        panel_url, clients = ssh_deployer.parse_deployment_results(sample_output)
        self.assertEqual(panel_url, "https://domain.com/path")
        self.assertEqual(len(clients), 1)
        self.assertEqual(clients[0]["name"], "Иван Иванов 🚀")
        self.assertEqual(clients[0]["xhttp_url"], "")


if __name__ == "__main__":
    unittest.main()
