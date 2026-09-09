#!/usr/bin/env python3
"""Unit test: Sub-server raw subscription list formatting."""

import base64
import http.client
import importlib.util
import json
import os
import sys
import shutil
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)


class TestSubServerHttpsRawList(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp(prefix="test_sub_https_")
        self.nodes_file = os.path.join(self.temp_dir, "nodes.json")
        self.force_file = os.path.join(self.temp_dir, "force-subs.yml")
        self.log_file = os.path.join(self.temp_dir, "sub-server.log")

        os.environ["NODES_FILE"] = self.nodes_file
        os.environ["FORCE_FILE"] = self.force_file
        os.environ["LOG_FILE"] = self.log_file
        os.environ["SECRET_SUB_PATH"] = "subs"
        os.environ["ADMIN_USER"] = "admin"
        os.environ["ADMIN_PASSWORD"] = "pass123"

        spec = importlib.util.spec_from_file_location(
            "sub_server_mod", os.path.join(REPO_ROOT, "sub-server", "server.py")
        )
        self.sub_mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.sub_mod)

        self.sub_mod.NODES = [
            {
                "id": "node1",
                "name": "Node 1",
                "url": "https://node1.example.com/subs",
                "clients": ["alice", "bob"],
            },
            {
                "id": "node2",
                "name": "Node 2",
                "url": "https://node2.example.com/subs",
                "clients": ["charlie"],
            },
        ]

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), self.sub_mod.Handler)
        self.port = self.server.server_address[1]
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2.0)
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_raw_subscription_list_formatting(self):
        auth_header = "Basic " + base64.b64encode(b"admin:pass123").decode("ascii")
        conn = http.client.HTTPConnection("127.0.0.1", self.port)
        conn.request(
            "GET",
            "/subs?raw=1",
            headers={
                "Host": "sub.example.com",
                "X-Forwarded-Proto": "https",
                "Authorization": auth_header,
            },
        )
        resp = conn.getresponse()
        body = resp.read().decode("utf-8")
        self.assertEqual(resp.status, 200)
        expected = (
            "alice,bob\n"
            "https://node1.example.com/subs/alice\n"
            "https://node1.example.com/subs/bob\n"
            "========================\n"
            "charlie\n"
            "https://node2.example.com/subs/charlie\n"
        )
        self.assertEqual(body, expected)
        conn.close()


if __name__ == "__main__":
    unittest.main()
