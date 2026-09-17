#!/usr/bin/env python3
"""Unit test: parse_deployment_results parses valid JSON output between markers."""

import os
import sys
import unittest

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

import ssh_deployer


class TestParseValidDeploymentOutput(unittest.TestCase):
    def test_valid_deployment_output(self):
        sample_output = """
        [INFO] Installing dependencies...
        [INFO] Setting up containers...
        ===RESULT_JSON_START===
        {
            "panel_url": "https://freedom.example.com:2053/secretpath/",
            "clients": [
                {
                    "name": "alice",
                    "sub_url": "https://freedom.example.com:2053/sub/alice",
                    "tcp_url": "vless://alice-uuid@freedom.example.com:443?type=tcp",
                    "xhttp_url": "vless://alice-uuid@freedom.example.com:443?type=xhttp"
                },
                {
                    "name": "bob",
                    "sub_url": "https://freedom.example.com:2053/sub/bob",
                    "tcp_url": "vless://bob-uuid@freedom.example.com:443?type=tcp",
                    "xhttp_url": "vless://bob-uuid@freedom.example.com:443?type=xhttp"
                }
            ]
        }
        ===RESULT_JSON_END===
        [SUCCESS] Deployment complete!
        """
        panel_url, clients = ssh_deployer.parse_deployment_results(sample_output)
        self.assertEqual(panel_url, "https://freedom.example.com:2053/secretpath/")
        self.assertEqual(len(clients), 2)
        self.assertEqual(clients[0]["name"], "alice")
        self.assertEqual(clients[0]["sub_url"], "https://freedom.example.com:2053/sub/alice")
        self.assertEqual(clients[1]["name"], "bob")


if __name__ == "__main__":
    unittest.main()
