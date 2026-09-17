#!/usr/bin/env python3
"""Smoke test for POST /api/config endpoint."""

import json
import os
import sys
import unittest
import urllib.request

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from tests.ui.ui_helpers import start_sandboxed_control_panel


class TestRoutingPostConfig(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server, cls.server_url, _, _, _ = start_sandboxed_control_panel("smoke_post_config")

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()

    def test_post_config(self):
        payload = {"common": {"vps_host": "example.com"}}
        url = f"{self.server_url}/api/config"
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            self.assertEqual(resp.status, 200)
            data = json.loads(resp.read().decode("utf-8"))
            self.assertTrue(data.get("ok"))


if __name__ == "__main__":
    unittest.main()
