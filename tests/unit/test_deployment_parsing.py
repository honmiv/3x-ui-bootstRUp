#!/usr/bin/env python3
"""
Unit, fuzz, and robustness tests for ssh_deployer parsing and utility functions.
Tests:
- parse_deployment_results:
  * standard markers and payloads
  * legacy / missing / corrupted / inverted markers
  * Unicode and special characters in URLs and client names
  * robustness / fuzz against malformed JSON, ANSI escape codes, nulls, huge strings, non-dict elements
- extract_domain_from_url:
  * schemes (http, https, vless), ports, paths, IP addresses, edge cases
- _sub_server_sync_cmd:
  * preserve=True (backup/restore of state files) vs preserve=False
"""

import json
import os
import sys
import unittest
from typing import List, Dict

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

import ssh_deployer


class TestParseDeploymentResults(unittest.TestCase):
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

    def test_empty_or_whitespace_output(self):
        self.assertEqual(ssh_deployer.parse_deployment_results(""), ("", []))
        self.assertEqual(ssh_deployer.parse_deployment_results("   \n\t  \n"), ("", []))

    def test_missing_start_or_end_marker(self):
        no_end = "===RESULT_JSON_START===\n{\"panel_url\": \"http://test\"}"
        no_start = "{\"panel_url\": \"http://test\"}\n===RESULT_JSON_END==="
        self.assertEqual(ssh_deployer.parse_deployment_results(no_end), ("", []))
        self.assertEqual(ssh_deployer.parse_deployment_results(no_start), ("", []))

    def test_inverted_markers(self):
        inverted = "===RESULT_JSON_END===\n{\"panel_url\": \"http://test\"}\n===RESULT_JSON_START==="
        self.assertEqual(ssh_deployer.parse_deployment_results(inverted), ("", []))

    def test_corrupted_json_between_markers(self):
        corrupted = """
        ===RESULT_JSON_START===
        { this is not valid json : [ }
        ===RESULT_JSON_END===
        """
        self.assertEqual(ssh_deployer.parse_deployment_results(corrupted), ("", []))

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


class TestExtractDomainFromUrl(unittest.TestCase):
    def test_standard_urls(self):
        self.assertEqual(ssh_deployer.extract_domain_from_url("https://sub.example.com"), "sub.example.com")
        self.assertEqual(ssh_deployer.extract_domain_from_url("http://example.com/"), "example.com")
        self.assertEqual(ssh_deployer.extract_domain_from_url("http://example.com/sub/path"), "example.com")

    def test_urls_with_ports(self):
        self.assertEqual(ssh_deployer.extract_domain_from_url("https://example.com:8443"), "example.com")
        self.assertEqual(ssh_deployer.extract_domain_from_url("http://node.test.org:2053/panel"), "node.test.org")

    def test_ip_addresses(self):
        self.assertEqual(ssh_deployer.extract_domain_from_url("http://192.168.1.50"), "192.168.1.50")
        self.assertEqual(ssh_deployer.extract_domain_from_url("https://10.0.0.1:8000/api"), "10.0.0.1")

    def test_custom_schemes_and_no_scheme(self):
        self.assertEqual(ssh_deployer.extract_domain_from_url("vless://user@domain.com:443"), "user@domain.com")
        self.assertEqual(ssh_deployer.extract_domain_from_url("naked-domain.com/path"), "naked-domain.com")

    def test_empty_and_whitespace(self):
        self.assertEqual(ssh_deployer.extract_domain_from_url(""), "")
        self.assertEqual(ssh_deployer.extract_domain_from_url("   "), "")
        self.assertEqual(ssh_deployer.extract_domain_from_url(None), "")


class TestSubServerSyncCommand(unittest.TestCase):
    def test_sync_cmd_with_preserve_true(self):
        cmd = ssh_deployer._sub_server_sync_cmd("/opt/3x-ui-bootstRUp", preserve=True)
        self.assertIn("mkdir -p /opt/3x-ui-bootstRUp", cmd)
        self.assertIn("tar -xzf - -C /opt/3x-ui-bootstRUp", cmd)
        self.assertIn("for f in subs.yml force-subs.yml nodes.json sub-server.log; do", cmd)
        self.assertIn("cp /opt/3x-ui-bootstRUp/sub-server/$f /tmp/sub-server-$f.bak", cmd)
        self.assertIn("cp /tmp/sub-server-$f.bak /opt/3x-ui-bootstRUp/sub-server/$f", cmd)
        self.assertIn("rm -f /tmp/sub-server-$f.bak", cmd)

    def test_sync_cmd_with_preserve_false(self):
        cmd = ssh_deployer._sub_server_sync_cmd("/custom/path", preserve=False)
        self.assertIn("mkdir -p /custom/path", cmd)
        self.assertIn("tar -xzf - -C /custom/path", cmd)
        self.assertNotIn("sub-server-$f.bak", cmd)
        self.assertIn("mkdir -p /custom/path && true && tar -xzf - -C /custom/path && true", cmd)


if __name__ == "__main__":
    unittest.main()

