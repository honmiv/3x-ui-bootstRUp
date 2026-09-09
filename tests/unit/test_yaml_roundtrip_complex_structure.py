#!/usr/bin/env python3
"""Unit test for YAML dump and load roundtrip with complex structure."""

import os
import sys
import unittest

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

import main


class TestYamlRoundtripComplex(unittest.TestCase):
    def test_roundtrip_complex_structure(self):
        original = {
            "common": {
                "deploy_mode": "cascade",
                "is_cascade": True,
                "custom_ssh_port": 2222,
            },
            "freedom_node": {
                "freedom_host": "192.168.1.100",
                "freedom_port": 22,
                "freedom_user": "root",
                "freedom_xui_version": "1.7.5",
            },
            "proxy_node": {
                "proxy_host": "proxy.example.com",
                "foreign_sub_url": "https://freedom.example.com/subs",
                "proxy_client_tcp_list": "client1,client2",
            }
        }
        dumped = main._dump_yaml_simple(original)
        loaded = main._load_yaml_simple(dumped)
        self.assertEqual(loaded, original)


if __name__ == "__main__":
    unittest.main()
