#!/usr/bin/env python3
"""Unit test for sub-server default nodes initialization from environment."""

import importlib.util
import os
import sys
import shutil
import tempfile
import unittest

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)


class TestSubServerNodesDefaultEnv(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp(prefix="test_sub_nodes_")
        self.nodes_file = os.path.join(self.temp_dir, "nodes.json")
        os.environ["NODES_FILE"] = self.nodes_file
        os.environ["SECRET_SUB_PATH"] = "subs"
        os.environ["PROXY_DOMAIN"] = "proxy.example.com"
        os.environ["FREEDOM_DOMAIN"] = "freedom.example.com"

        spec = importlib.util.spec_from_file_location(
            "sub_server_mod_nodes", os.path.join(REPO_ROOT, "sub-server", "server.py")
        )
        self.sub_mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.sub_mod)

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_default_nodes_env_domain(self):
        os.environ["RUSSIAN_SUB_URL"] = "https://proxy.example.com/subs"
        os.environ["FOREIGN_SUB_URL"] = "https://freedom.example.com/subs"
        self.sub_mod.RUSSIAN_SUB_URL = "https://proxy.example.com/subs"
        self.sub_mod.FOREIGN_SUB_URL = "https://freedom.example.com/subs"

        nodes = self.sub_mod.default_nodes()
        self.assertEqual(len(nodes), 2)
        self.assertEqual(nodes[0]["type"], "proxy")
        self.assertEqual(nodes[0]["name"], "proxy.example.com")
        self.assertEqual(nodes[1]["type"], "freedom")
        self.assertEqual(nodes[1]["name"], "freedom.example.com")


if __name__ == "__main__":
    unittest.main()
