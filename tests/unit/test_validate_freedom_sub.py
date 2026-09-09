#!/usr/bin/env python3
"""Unit test for validate_deployment_config in freedom_sub mode."""

import os
import sys
import unittest

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from ssh_deployer import validate_deployment_config


class TestValidateFreedomSub(unittest.TestCase):
    def test_freedom_sub_validation(self):
        base_freedom = {
            "deploy_mode": "freedom_sub",
            "vps_host": "freedom.com",
            "vps_port": 22,
            "vps_user": "root",
            "vps_password": "pass",
            "xui_username": "admin",
            "xui_password": "pass",
            "sub_secret": "secret",
            "sub_vps_host": "sub.com",
            "sub_vps_port": 22,
            "sub_vps_user": "root",
            "sub_vps_password": "pass",
            "sub_secret_path": "my_subs",
            "sub_admin_user": "admin",
            "sub_admin_password": "pass",
        }

        # Missing both TCP and XHTTP clients
        ok, msg = validate_deployment_config({
            **base_freedom,
            "client_tcp_list": "",
            "client_xhttp_list": "",
        })
        self.assertFalse(ok)
        self.assertIn("хотя бы одного клиента", msg.lower())

        # Missing Sub-server credentials
        ok, msg = validate_deployment_config({
            **base_freedom,
            "client_tcp_list": "client1",
            "sub_vps_host": "",
        })
        self.assertFalse(ok)
        self.assertIn("сервера подписок", msg.lower())

        # Valid freedom_sub
        ok, msg = validate_deployment_config({
            **base_freedom,
            "client_tcp_list": "client1",
        })
        self.assertTrue(ok)
        self.assertEqual(msg, "")


if __name__ == "__main__":
    unittest.main()
