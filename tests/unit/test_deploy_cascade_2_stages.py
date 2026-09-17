#!/usr/bin/env python3
"""Unit test for deploy_cascade 2-stage orchestration."""

import asyncio
import os
import sys
import unittest
from unittest.mock import patch

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from deployers.panel_deployer import deploy_cascade


class TestDeployCascade2Stages(unittest.TestCase):
    def test_deploy_cascade_2_stages(self):
        config = {
            "deploy_mode": "cascade",
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
        }

        captured_nodes = []

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

        logs = []
        with patch("deployers.panel_deployer._deploy_node", side_effect=fake_deploy_node):
            ok, result = asyncio.run(
                deploy_cascade(
                    config=config,
                    log=lambda m, lvl: logs.append((m, lvl)),
                    prepare_decoy_files=lambda tpl, lbl: None,
                )
            )

        self.assertTrue(ok)
        self.assertEqual(len(captured_nodes), 2)

        # Stage 1: Freedom Node
        node1 = captured_nodes[0]
        self.assertEqual(node1.host, "freedom.vps.example")
        self.assertEqual(node1.env_vars["CASCADE_CHOICE"], "y")
        self.assertEqual(node1.env_vars["NODE_TYPE_CHOICE"], "1")
        self.assertEqual(node1.env_vars["CLIENTS_XHTTP_LIST"], "relay-client")

        # Stage 2: Proxy Node
        node2 = captured_nodes[1]
        self.assertEqual(node2.host, "proxy.vps.example")
        self.assertEqual(node2.env_vars["CASCADE_CHOICE"], "y")
        self.assertEqual(node2.env_vars["NODE_TYPE_CHOICE"], "2")
        self.assertEqual(node2.env_vars["FOREIGN_SUB_URL"], "https://freedom.vps.example/f-sub/relay-client")
        self.assertEqual(node2.env_vars["CLIENTS_TCP_LIST"], "user1")
        self.assertEqual(node2.env_vars["CLIENTS_XHTTP_LIST"], "user2")

        # Result verification
        self.assertTrue(result.get("is_cascade"))
        self.assertEqual(len(result["clients"]), 2)


if __name__ == "__main__":
    unittest.main()
