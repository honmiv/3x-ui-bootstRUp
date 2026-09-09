#!/usr/bin/env python3
"""Smoke test for GET /api/decoys endpoint."""

import json
import os
import sys
import unittest
import urllib.request

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from tests.ui.ui_helpers import start_sandboxed_control_panel


class TestRoutingGetDecoys(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server, cls.server_url, _, _, _ = start_sandboxed_control_panel("smoke_decoys")

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()

    def test_get_decoys(self):
        url = f"{self.server_url}/api/decoys"
        with urllib.request.urlopen(urllib.request.Request(url), timeout=5) as resp:
            self.assertEqual(resp.status, 200)
            data = json.loads(resp.read().decode("utf-8"))
            self.assertTrue(data.get("ok"))
            self.assertIn("decoys", data)


if __name__ == "__main__":
    unittest.main()
