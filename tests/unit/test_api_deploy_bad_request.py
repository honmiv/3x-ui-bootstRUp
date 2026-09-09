#!/usr/bin/env python3
"""Integration test: POST /api/deploy returns HTTP 400 Bad Request on validation failure."""

import json
import os
import sys
import unittest
import urllib.error
import urllib.request

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from tests.ui.ui_helpers import start_sandboxed_control_panel


class TestApiDeployBadRequest(unittest.TestCase):
    def test_api_deploy_400_bad_request(self):
        server, server_url, _, _, _ = start_sandboxed_control_panel("api_validation_test")
        try:
            # Send invalid deploy payload (missing xui_username)
            payload = {
                "deploy_mode": "single",
                "vps_host": "test.example.com",
                "vps_port": 22,
                "vps_user": "root",
                "vps_password": "password123",
                "xui_username": "",
                "xui_password": "password123",
                "sub_secret": "secret"
            }
            req = urllib.request.Request(
                f"{server_url}/api/deploy",
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"}
            )
            with self.assertRaises(urllib.error.HTTPError) as ctx:
                urllib.request.urlopen(req)
            self.assertEqual(ctx.exception.code, 400)
            resp_body = json.loads(ctx.exception.read().decode("utf-8"))
            self.assertFalse(resp_body.get("ok"))
            self.assertIn("логин админа", resp_body.get("message", "").lower())
        finally:
            server.shutdown()


if __name__ == "__main__":
    unittest.main()
