#!/usr/bin/env python3
"""Unit tests for deploy_freedom_sub env_vars assembly (Phase C3).

Verifies:
1. Stage 1 (Freedom node) env_vars:
   - DOMAIN, USERNAME, USER_PASSWORD, XUI_VERSION, SECRET_PHRASE
   - CASCADE_CHOICE="y", NODE_TYPE_CHOICE="1", FOREIGN_SUB_URL=""
   - Client lists (TCP/XHTTP).
2. Stage 2 (Subscription server) env_vars:
   - DOMAIN, SECRET_SUB_PATH, FOREIGN_SUB_URL, RUSSIAN_SUB_URL=""
   - FREEDOM_DOMAIN correctly falls back to target_domain or host without NameError
   - FREEDOM_CLIENTS contains client names from both TCP and XHTTP lists
   - ADMIN_USER, ADMIN_PASSWORD.
3. Proper result_data construction with sub_server_url assigned to clients.
"""

import asyncio
import os
import sys
import unittest
from unittest.mock import AsyncMock, patch

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from deployers.panel_deployer import deploy_freedom_sub


class TestDeployFreedomSubEnv(unittest.TestCase):
    def test_deploy_freedom_sub_env_vars_and_fallback(self):
        config = {
            "deploy_mode": "freedom_sub",
            "vps_host": "freedom.vps.example",
            "vps_port": 22,
            "vps_user": "root",
            "vps_password": "freedom_ssh_password",
            "domain": "",  # Empty to test fallback to host
            "xui_username": "freedom_admin",
            "xui_password": "freedom_admin_pass",
            "xui_version": "2.4.0",
            "sub_secret": "freedom_secret_phrase",
            "client_tcp_list": "alice bob",
            "client_xhttp_list": "charlie",
            "sub_vps_host": "sub.vps.example",
            "sub_vps_port": 2222,
            "sub_vps_user": "subroot",
            "sub_vps_password": "sub_ssh_password",
            "sub_domain": "sub.domain.example",
            "sub_secret_path": "custom_subs",
            "sub_admin_user": "subadmin",
            "sub_admin_password": "subpassword123",
        }

        captured_node_configs = []

        async def fake_deploy_node(node, log):
            captured_node_configs.append(("node", node))
            # Mock output containing result marker
            output = (
                "===RESULT_JSON_START===\n"
                '{"xui_url": "https://freedom.vps.example/web_path/", "clients": ['
                '{"name": "alice", "sub_url": "https://freedom.vps.example/sub_path/alice"},'
                '{"name": "bob", "sub_url": "https://freedom.vps.example/sub_path/bob"},'
                '{"name": "charlie", "sub_url": "https://freedom.vps.example/sub_path/charlie"}'
                "]}\n"
                "===RESULT_JSON_END==="
            )
            return True, output

        async def fake_deploy_sub_server(node, log):
            captured_node_configs.append(("sub_server", node))
            return True, "SUB_SERVER_DEPLOYED_OK"

        logs = []
        with patch("deployers.panel_deployer._deploy_node", side_effect=fake_deploy_node), \
             patch("deployers.panel_deployer._deploy_sub_server", side_effect=fake_deploy_sub_server):
            ok, result = asyncio.run(
                deploy_freedom_sub(
                    config=config,
                    log=lambda m, lvl: logs.append((m, lvl)),
                    prepare_decoy_files=lambda tpl, lbl: None,
                )
            )

        self.assertTrue(ok)
        self.assertEqual(len(captured_node_configs), 2)

        # 1. Verify Stage 1 (Freedom node)
        stage1_type, stage1_node = captured_node_configs[0]
        self.assertEqual(stage1_type, "node")
        self.assertEqual(stage1_node.host, "freedom.vps.example")
        s1_env = stage1_node.env_vars
        self.assertEqual(s1_env["DOMAIN"], "freedom.vps.example")
        self.assertEqual(s1_env["USERNAME"], "freedom_admin")
        self.assertEqual(s1_env["USER_PASSWORD"], "freedom_admin_pass")
        self.assertEqual(s1_env["XUI_VERSION"], "2.4.0")
        self.assertEqual(s1_env["CASCADE_CHOICE"], "y")
        self.assertEqual(s1_env["NODE_TYPE_CHOICE"], "1")
        self.assertEqual(s1_env["FOREIGN_SUB_URL"], "")
        self.assertEqual(s1_env["CLIENTS_TCP_LIST"], "alice bob")
        self.assertEqual(s1_env["CLIENTS_XHTTP_LIST"], "charlie")

        # 2. Verify Stage 2 (Subscription server)
        stage2_type, stage2_node = captured_node_configs[1]
        self.assertEqual(stage2_type, "sub_server")
        self.assertEqual(stage2_node.host, "sub.vps.example")
        self.assertEqual(stage2_node.port, 2222)
        s2_env = stage2_node.env_vars
        self.assertEqual(s2_env["DOMAIN"], "sub.domain.example")
        self.assertEqual(s2_env["RUSSIAN_SUB_URL"], "")
        self.assertEqual(s2_env["FOREIGN_SUB_URL"], "https://freedom.vps.example/sub_path")
        # Line 225 bug verification: fr_domain must be freedom.vps.example without NameError
        self.assertEqual(s2_env["FREEDOM_DOMAIN"], "freedom.vps.example")
        self.assertEqual(s2_env["PROXY_DOMAIN"], "")
        self.assertIn("alice", s2_env["FREEDOM_CLIENTS"])
        self.assertIn("bob", s2_env["FREEDOM_CLIENTS"])
        self.assertIn("charlie", s2_env["FREEDOM_CLIENTS"])
        self.assertEqual(s2_env["ADMIN_USER"], "subadmin")
        self.assertEqual(s2_env["ADMIN_PASSWORD"], "subpassword123")

        # 3. Verify Result data
        self.assertEqual(result["deploy_mode"], "freedom_sub")
        self.assertEqual(result["sub_domain"], "sub.domain.example")
        self.assertEqual(len(result["clients"]), 3)
        for cl in result["clients"]:
            self.assertIn("sub_server_url", cl)
            self.assertTrue(cl["sub_server_url"].startswith("https://sub.domain.example/"))


if __name__ == "__main__":
    unittest.main()

