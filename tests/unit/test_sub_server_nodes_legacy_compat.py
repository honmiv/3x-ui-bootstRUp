#!/usr/bin/env python3
"""Unit test for sub-server backward compatibility with legacy nodes format."""

import importlib.util
import json
import os
import sys
import shutil
import tempfile
import unittest

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)


class TestSubServerNodesLegacyCompat(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp(prefix="test_sub_nodes_")
        self.nodes_file = os.path.join(self.temp_dir, "nodes.json")
        os.environ["NODES_FILE"] = self.nodes_file
        os.environ["SECRET_SUB_PATH"] = "subs"

        spec = importlib.util.spec_from_file_location(
            "sub_server_mod_nodes", os.path.join(REPO_ROOT, "sub-server", "server.py")
        )
        self.sub_mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.sub_mod)

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_legacy_nodes_backward_compatibility(self):
        with open(self.nodes_file, "w", encoding="utf-8") as f:
            json.dump([
                {"id": "proxy", "name": "Proxy (РФ)", "url": "https://ru-node.example.org/subs", "clients": ["alice"]},
                {"id": "freedom", "name": "Freedom (зарубежье)", "url": "https://eu-node.example.org/subs", "clients": ["bob"]},
            ], f)

        nodes = self.sub_mod.load_nodes(self.nodes_file)
        self.assertEqual(len(nodes), 2)
        self.assertEqual(nodes[0]["type"], "proxy")
        self.assertEqual(nodes[0]["name"], "ru-node.example.org")
        self.assertEqual(nodes[1]["type"], "freedom")
        self.assertEqual(nodes[1]["name"], "eu-node.example.org")


if __name__ == "__main__":
    unittest.main()
