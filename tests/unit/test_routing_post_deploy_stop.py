#!/usr/bin/env python3
"""Smoke test: POST /api/deploy/stop behavior in idle (400) and running (200) states."""

import json
import os
import sys
import unittest
import urllib.error
import urllib.request

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

import main as backend_main
from tests.ui.ui_helpers import start_sandboxed_control_panel


class TestRoutingPostDeployStop(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server, cls.server_url, _, _, _ = start_sandboxed_control_panel("smoke_deploy_stop")

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()

    def test_post_deploy_stop_idle_and_running(self):
        # 1. Idle state: returns 400 Bad Request
        url = f"{self.server_url}/api/deploy/stop"
        req = urllib.request.Request(
            url,
            data=json.dumps({}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            urllib.request.urlopen(req, timeout=5)
        self.assertEqual(ctx.exception.code, 400)
        resp_data = json.loads(ctx.exception.read().decode("utf-8"))
        self.assertFalse(resp_data.get("ok"))

        # 2. Active deploying state: returns 200 OK
        try:
            backend_main.is_deploying = True
            req2 = urllib.request.Request(
                url,
                data=json.dumps({}).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req2, timeout=5) as resp:
                self.assertEqual(resp.status, 200)
                data = json.loads(resp.read().decode("utf-8"))
                self.assertTrue(data.get("ok"))
                self.assertTrue(backend_main.cancel_requested)
        finally:
            backend_main.is_deploying = False
            backend_main.cancel_requested = False


if __name__ == "__main__":
    unittest.main()
