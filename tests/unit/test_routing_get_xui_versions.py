#!/usr/bin/env python3
"""Smoke test for GET /api/xui_versions endpoint."""

import json
import os
import sys
import unittest
import urllib.request

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from tests.ui.ui_helpers import start_sandboxed_control_panel


class TestRoutingGetXuiVersions(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import time
        import main as backend_main
        with backend_main.CACHE_LOCK:
            backend_main.XUI_CACHE["data"] = ["latest", "3.6.0", "3.5.8"]
            backend_main.XUI_CACHE["ts"] = time.time()
        cls.server, cls.server_url, _, _, _ = start_sandboxed_control_panel("smoke_xui_versions")

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()

    def test_get_xui_versions(self):
        url = f"{self.server_url}/api/xui_versions"
        with urllib.request.urlopen(urllib.request.Request(url), timeout=5) as resp:
            self.assertEqual(resp.status, 200)
            data = json.loads(resp.read().decode("utf-8"))
            self.assertIn("versions", data)
            self.assertIsInstance(data["versions"], list)
            self.assertGreater(len(data["versions"]), 0)

    def test_fetch_xui_versions_fallback_on_network_error(self):
        import main as backend_main
        from unittest.mock import patch
        with backend_main.CACHE_LOCK:
            backend_main.XUI_CACHE["data"] = None
            backend_main.XUI_CACHE["ts"] = 0.0
        with patch("urllib.request.urlopen", side_effect=OSError("Network unreachable")):
            versions = backend_main.fetch_xui_versions()
            self.assertEqual(versions, ["latest"])


if __name__ == "__main__":
    unittest.main()
