#!/usr/bin/env python3
"""Unit test for Subscription Server update env_vars and remote backup."""

import asyncio
import os
import sys
import unittest
from unittest.mock import patch

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from deployers.maintenance import deploy_sub_ops


class TestUpdateDeployEnvVarsAndBackup(unittest.TestCase):
    def test_update_deploy_env_vars_and_backup(self):
        config = {
            "deploy_mode": "update_sub",
            "sub_vps_host": "sub.vps.example",
            "sub_vps_port": 22,
            "sub_vps_user": "root",
            "sub_vps_password": "password",
            "update_sub_decoy_template": "company",
        }

        captured_node = []
        backup_called = []

        async def fake_deploy_sub_server(node, log):
            captured_node.append(node)
            return True, "UPDATE_SUB_OK"

        async def fake_perform_remote_backup(deployer, backup_name, log, target="panel"):
            backup_called.append((backup_name, target))
            return True, f"./backups_sub_server/{backup_name}", "1.5"

        class FakeSSHDeployer:
            def __init__(self, *args, **kwargs):
                pass
            async def __aenter__(self):
                return self
            async def __aexit__(self, exc_type, exc_val, exc_tb):
                pass
            async def test_connection(self):
                return True, ""
            async def exec_command(self, cmd, *args, **kwargs):
                if "Caddyfile" in cmd:
                    return 0, "email test@sub.domain.example"
                return 0, "OK"

        logs = []
        with patch("deployers.maintenance.SSHDeployer", FakeSSHDeployer), \
             patch("deployers.maintenance._perform_remote_backup", side_effect=fake_perform_remote_backup), \
             patch("deployers.maintenance._deploy_sub_server", side_effect=fake_deploy_sub_server):
            ok, result = asyncio.run(
                deploy_sub_ops(
                    config=config,
                    log=lambda m, lvl: logs.append((m, lvl)),
                    prepare_decoy_files=lambda tpl, lbl: {"index.html": b"<html>"},
                )
            )

        self.assertTrue(ok)
        self.assertEqual(len(backup_called), 1)
        self.assertEqual(backup_called[0][1], "sub_server")

        self.assertEqual(len(captured_node), 1)
        env = captured_node[0].env_vars
        self.assertEqual(env.get("UPDATE_SUB_SERVER"), "1")
        self.assertEqual(env.get("UPDATE_SUB_DECOY"), "1")

        # Crucial security & data integrity invariant:
        # DOMAIN, ADMIN_USER, ADMIN_PASSWORD must NOT be present in update env
        self.assertNotIn("DOMAIN", env)
        self.assertNotIn("ADMIN_USER", env)
        self.assertNotIn("ADMIN_PASSWORD", env)


if __name__ == "__main__":
    unittest.main()
