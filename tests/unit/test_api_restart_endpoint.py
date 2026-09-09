#!/usr/bin/env python3
"""API response test: POST /api/restart responds with JSON."""

import http.client
import json
import os
import sys
import threading
import unittest
from unittest.mock import patch
from http.server import HTTPServer

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

import main as backend_main


class TestApiRestartEndpoint(unittest.TestCase):
    def test_restart_endpoint_responds_json(self):
        backend_main.is_deploying = False
        server = HTTPServer(("127.0.0.1", 0), backend_main.WebUIHandler)
        port = server.server_address[1]
        t = threading.Thread(target=server.serve_forever, daemon=True)
        t.start()
        try:
            with patch("routing.threading.Thread"):
                conn = http.client.HTTPConnection("127.0.0.1", port)
                conn.request("POST", "/api/restart")
                resp = conn.getresponse()
                data = json.loads(resp.read().decode("utf-8"))
                conn.close()
                self.assertEqual(resp.status, 200)
                self.assertIn("ok", data)
        finally:
            server.shutdown()
            server.server_close()
            t.join(timeout=2.0)


if __name__ == "__main__":
    unittest.main()
