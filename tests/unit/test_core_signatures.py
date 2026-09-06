#!/usr/bin/env python3
"""
Signature and API contract snapshot tests for core functions.
Guarantees that subsequent refactoring phases (such as splitting ssh_deployer.py
into deployers/ and moving main.py routes) do not accidentally break or change
public signatures, parameter names, or defaults expected by callers and test overrides.
"""

import inspect
import os
import sys
import unittest

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

import main
import ssh_deployer


class TestCoreSignatures(unittest.TestCase):
    def _assert_params(self, func, expected_params):
        sig = inspect.signature(func)
        actual_params = list(sig.parameters.keys())
        self.assertEqual(
            actual_params,
            expected_params,
            f"Signature parameters mismatch for {func.__qualname__}: {actual_params} != {expected_params}"
        )

    def test_ssh_deployer_run_deployment_signature(self):
        sig = inspect.signature(ssh_deployer.run_deployment)
        params = list(sig.parameters.values())
        self.assertEqual([p.name for p in params], ["config", "log_callback", "cancel_check"])
        self.assertIsNot(params[2].default, inspect.Parameter.empty)
        self.assertIsNone(params[2].default)

    def test_ssh_deployer_parse_deployment_results_signature(self):
        self._assert_params(ssh_deployer.parse_deployment_results, ["output_text"])

    def test_ssh_deployer_derive_sub_paths_signature(self):
        self._assert_params(ssh_deployer.derive_sub_path, ["secret"])
        self._assert_params(ssh_deployer.derive_sub_server_path, ["secret"])

    def test_ssh_deployer_resolve_sub_server_urls_signature(self):
        self._assert_params(
            ssh_deployer.resolve_sub_server_urls,
            ["proxy_sub_url", "freedom_sub_url"]
        )

    def test_ssh_deployer_extract_domain_from_url_signature(self):
        self._assert_params(ssh_deployer.extract_domain_from_url, ["url"])

    def test_ssh_deployer_sub_server_sync_cmd_signature(self):
        self._assert_params(ssh_deployer._sub_server_sync_cmd, ["remote_dir", "preserve"])

    def test_ssh_deployer_ssh_client_methods(self):
        self.assertTrue(hasattr(ssh_deployer.SSHDeployer, "exec_command"))
        self.assertTrue(hasattr(ssh_deployer.SSHDeployer, "download_file"))
        self.assertTrue(hasattr(ssh_deployer.SSHDeployer, "test_connection"))

    def test_main_config_persistence_signatures(self):
        self._assert_params(main.save_backup_config, ["data"])
        self._assert_params(main.load_backup_config, [])

    def test_main_yaml_signatures(self):
        self._assert_params(main._dump_yaml_simple, ["data"])
        self._assert_params(main._load_yaml_simple, ["text"])
        self._assert_params(main._parse_yaml_scalar, ["val_str"])

    def test_main_public_utilities_signatures(self):
        self._assert_params(main.fetch_xui_versions, [])
        self._assert_params(main.check_for_update, ["force"])
        self._assert_params(main.list_backup_files, ["folder"])


if __name__ == "__main__":
    unittest.main()
