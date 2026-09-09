#!/usr/bin/env python3
"""Unit test for deploy_cascade 3-stage orchestration (cascade_sub)."""

import asyncio
import os
import sys
import unittest
from unittest.mock import patch

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from deployers.panel_deployer import deploy_cascade


class TestDeployCascadeSub3Stages(unittest.TestCase):
    def test_deploy_cascade_sub_3_stages(self):
        config = {
            "deploy_mode": "cascade_sub",
            "xui_version": "2.4.0",
            "freedom_host": "freedom.vps.example",
            "freedom_port": 22,
            "freedom_user": "root",
            "freedom_password": "freedom_pass",
            "freedom_xui_username": "freedom_admin",
            "freedom_xui_password": "freedom_pass",
            "freedom_sub_secret": "freedom_secret",
            "freedom_client_name": "relay-client",
            "proxy_host": "proxy.vps.example",
            "proxy_port": 22,
            "proxy_user": "root",
            "proxy_password": "proxy_pass",
            "proxy_xui_username": "proxy_admin",
            "proxy_xui_password": "proxy_pass",
            "proxy_sub_secret": "proxy_secret",
            "proxy_client_tcp_list": "user1",
            "proxy_client_xhttp_list": "user2",
            "sub_vps_host": "sub.vps.example",
            "sub_vps_port": 22,
            "sub_vps_user": "root",
            "sub_vps_password": "sub_pass",
            "sub_domain": "sub.domain.example",
            "sub_secret_path": "subs_key",
            "sub_admin_user": "admin",
            "sub_admin_password": "admin_pass",
        }

        captured_nodes = []
        captured_subs = []

        async def fake_deploy_node(node, log):
            captured_nodes.append(node)
            if node.host == "freedom.vps.example":
                out = (
                    "===RESULT_JSON_START===\n"
                    '{"xui_url": "https://freedom.vps.example/f-panel/", "clients": ['
                    '{"name": "relay-client", "sub_url": "https://freedom.vps.example/f-sub/relay-client"}'
                    ']}\n'
                    "===RESULT_JSON_END==="
                )
            else:
                out = (
                    "===RESULT_JSON_START===\n"
                    '{"xui_url": "https://proxy.vps.example/p-panel/", "clients": ['
                    '{"name": "user1", "sub_url": "https://proxy.vps.example/p-sub/user1"},'
                    '{"name": "user2", "sub_url": "https://proxy.vps.example/p-sub/user2"}'
                    ']}\n'
                    "===RESULT_JSON_END==="
                )
            return True, out

        async def fake_deploy_sub(node, log):
            captured_subs.append(node)
            return True, "SUB_OK"

        logs = []
        with patch("deployers.panel_deployer._deploy_node", side_effect=fake_deploy_node), \
             patch("deployers.panel_deployer._deploy_sub_server", side_effect=fake_deploy_sub):
            ok, result = asyncio.run(
                deploy_cascade(
                    config=config,
                    log=lambda m, lvl: logs.append((m, lvl)),
                    prepare_decoy_files=lambda tpl, lbl: None,
                )
            )

        self.assertTrue(ok)
        self.assertEqual(len(captured_nodes), 2)
        self.assertEqual(len(captured_subs), 1)

        # Stage 3: Sub-Server Node
        sub_node = captured_subs[0]
        self.assertEqual(sub_node.host, "sub.vps.example")
        sub_env = sub_node.env_vars
        self.assertEqual(sub_env["DOMAIN"], "sub.domain.example")
        self.assertEqual(sub_env["RUSSIAN_SUB_URL"], "https://proxy.vps.example/p-sub")
        self.assertEqual(sub_env["FOREIGN_SUB_URL"], "https://freedom.vps.example/f-sub")
        self.assertEqual(sub_env["PROXY_DOMAIN"], "proxy.vps.example")
        self.assertEqual(sub_env["FREEDOM_DOMAIN"], "freedom.vps.example")
        self.assertIn("user1", sub_env["PROXY_CLIENTS"])
        self.assertIn("user2", sub_env["PROXY_CLIENTS"])
        self.assertEqual(sub_env["FREEDOM_CLIENTS"], "relay-client")

        # Result verification
        self.assertEqual(result["sub_domain"], "sub.domain.example")
        for cl in result["clients"]:
            self.assertIn("sub_server_url", cl)
            self.assertTrue(cl["sub_server_url"].startswith("https://sub.domain.example/"))


if __name__ == "__main__":
    unittest.main()
