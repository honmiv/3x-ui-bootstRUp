#!/usr/bin/env python3
"""Unit test for Subscription Server fresh deploy env_vars."""

import asyncio
import os
import sys
import unittest
from unittest.mock import patch

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from deployers.sub_deployer import deploy_sub_only


class TestFreshDeployEnvVars(unittest.TestCase):
    def test_fresh_deploy_env_vars(self):
        config = {
            "deploy_mode": "sub_only",
            "sub_vps_host": "sub.vps.example",
            "sub_vps_port": 22,
            "sub_vps_user": "root",
            "sub_vps_password": "password",
            "sub_domain": "sub.domain.example",
            "sub_secret_path": "my_subs",
            "sub_russian_url": "https://ru.proxy.com/subs",
            "sub_foreign_url": "https://foreign.node.com/subs",
            "sub_proxy_clients": "client_ru_1 client_ru_2",
            "sub_freedom_clients": "client_fr_1",
            "sub_admin_user": "admin123",
            "sub_admin_password": "supersecretpassword",
        }

        captured_node = []

        async def fake_deploy_sub_server(node, log):
            captured_node.append(node)
            return True, "FRESH_SUB_OK"

        logs = []
        with patch("deployers.sub_deployer._deploy_sub_server", side_effect=fake_deploy_sub_server):
            ok, result = asyncio.run(
                deploy_sub_only(
                    config=config,
                    log=lambda m, lvl: logs.append((m, lvl)),
                    prepare_decoy_files=lambda tpl, lbl: None,
                )
            )

        self.assertTrue(ok)
        self.assertEqual(len(captured_node), 1)
        env = captured_node[0].env_vars

        self.assertEqual(env["DOMAIN"], "sub.domain.example")
        self.assertEqual(env["ADMIN_USER"], "admin123")
        self.assertEqual(env["ADMIN_PASSWORD"], "supersecretpassword")
        self.assertIn("client_ru_1", env["PROXY_CLIENTS"])
        self.assertIn("client_fr_1", env["FREEDOM_CLIENTS"])
        self.assertNotIn("UPDATE_SUB_SERVER", env)


if __name__ == "__main__":
    unittest.main()
