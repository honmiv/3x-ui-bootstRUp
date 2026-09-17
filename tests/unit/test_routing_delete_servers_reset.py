#!/usr/bin/env python3
"""Smoke test for DELETE /api/servers/reset endpoint."""

import json
import os
import sys
import unittest
import urllib.request

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from tests.ui.ui_helpers import start_sandboxed_control_panel


class TestRoutingDeleteServersReset(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server, cls.server_url, _, _, _ = start_sandboxed_control_panel("smoke_servers_reset")

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()

    def test_delete_servers_reset(self):
        url = f"{self.server_url}/api/servers/reset"
        req = urllib.request.Request(url, method="DELETE")
        with urllib.request.urlopen(req, timeout=5) as resp:
            self.assertEqual(resp.status, 200)
            data = json.loads(resp.read().decode("utf-8"))
            self.assertTrue(data.get("ok"))


if __name__ == "__main__":
    unittest.main()
