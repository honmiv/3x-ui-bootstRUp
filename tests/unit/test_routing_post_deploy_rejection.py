#!/usr/bin/env python3
"""Smoke test: POST /api/deploy rejects invalid payload with HTTP 400."""

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


class TestRoutingPostDeployRejection(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server, cls.server_url, _, _, _ = start_sandboxed_control_panel("smoke_deploy_rejection")

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()

    def test_post_deploy_validation_rejection(self):
        url = f"{self.server_url}/api/deploy"
        req = urllib.request.Request(
            url,
            data=json.dumps({"deploy_mode": "single"}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            urllib.request.urlopen(req, timeout=5)
        self.assertEqual(ctx.exception.code, 400)
        resp_data = json.loads(ctx.exception.read().decode("utf-8"))
        self.assertFalse(resp_data.get("ok"))


if __name__ == "__main__":
    unittest.main()
