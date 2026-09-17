#!/usr/bin/env python3
"""Smoke test for GET /api/status endpoint."""

import json
import os
import sys
import unittest
import urllib.request

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from tests.ui.ui_helpers import start_sandboxed_control_panel


class TestRoutingGetStatus(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server, cls.server_url, _, _, _ = start_sandboxed_control_panel("smoke_status")

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()

    def test_get_status(self):
        url = f"{self.server_url}/api/status"
        with urllib.request.urlopen(urllib.request.Request(url), timeout=5) as resp:
            self.assertEqual(resp.status, 200)
            data = json.loads(resp.read().decode("utf-8"))
            self.assertIn("deploying", data)
            self.assertIn("status", data)


if __name__ == "__main__":
    unittest.main()
