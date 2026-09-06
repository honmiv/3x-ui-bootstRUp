#!/usr/bin/env python3
"""
Unit and security tests for YAML serialization, parsing, and setup_backup.yml persistence.
Tests:
- _parse_yaml_scalar edge cases (booleans, ints, floats, nulls, escaped quotes, comments).
- _dump_yaml_simple formatting, escaping, section nesting, and empty section pruning.
- _load_yaml_simple line parsing, section indentation, multiline blocks (| and quotes).
- YAML roundtrip idempotency for config payloads.
- Security assertions: passwords and private keys (*_key) are NEVER persisted to disk.
"""

import os
import re
import sys
import tempfile
import unittest
from typing import Dict, Any

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

import main


class TestYamlScalarParser(unittest.TestCase):
    def test_parse_booleans(self):
        for raw, expected in [
            ("true", True), ("True", True), ("TRUE", True),
            ("yes", True), ("Yes", True), ("on", True),
            ("false", False), ("False", False), ("FALSE", False),
            ("no", False), ("No", False), ("off", False),
        ]:
            self.assertEqual(main._parse_yaml_scalar(raw), expected, f"Failed for {raw}")

    def test_parse_nulls(self):
        for raw in ["null", "Null", "NULL", "none", "None", "~"]:
            self.assertIsNone(main._parse_yaml_scalar(raw), f"Failed for {raw}")

    def test_parse_numbers(self):
        self.assertEqual(main._parse_yaml_scalar("42"), 42)
        self.assertEqual(main._parse_yaml_scalar("-10"), -10)
        self.assertEqual(main._parse_yaml_scalar("0"), 0)
        self.assertEqual(main._parse_yaml_scalar("3.14"), 3.14)
        self.assertEqual(main._parse_yaml_scalar("-0.5"), -0.5)

    def test_parse_strings_and_quotes(self):
        self.assertEqual(main._parse_yaml_scalar('"hello world"'), "hello world")
        self.assertEqual(main._parse_yaml_scalar("'simple string'"), "simple string")
        self.assertEqual(main._parse_yaml_scalar('"line1\\nline2"'), "line1\nline2")
        self.assertEqual(main._parse_yaml_scalar('"escaped \\"quotes\\""'), 'escaped "quotes"')
        self.assertEqual(main._parse_yaml_scalar('"tab\\there"'), "tab\there")
        self.assertEqual(main._parse_yaml_scalar("'it''s fine'"), "it's fine")

    def test_parse_inline_comments(self):
        self.assertEqual(main._parse_yaml_scalar("example.com # server domain"), "example.com")
        self.assertEqual(main._parse_yaml_scalar("8080 # port"), 8080)
        self.assertEqual(main._parse_yaml_scalar("true # enable feature"), True)

    def test_parse_empty(self):
        self.assertEqual(main._parse_yaml_scalar(""), "")
        self.assertEqual(main._parse_yaml_scalar("   "), "")


class TestYamlDumpAndLoad(unittest.TestCase):
    def test_dump_format_and_escaping(self):
        data = {
            "section1": {
                "host": "example.com",
                "port": 443,
                "enabled": True,
                "disabled": False,
                "empty_str": "",
                "with_colon": "foo:bar",
                "with_hash": "foo#bar",
            }
        }
        dumped = main._dump_yaml_simple(data)
        self.assertIn("section1:", dumped)
        self.assertIn("host: example.com", dumped)
        self.assertIn("port: 443", dumped)
        self.assertIn("enabled: true", dumped)
        self.assertIn("disabled: false", dumped)
        self.assertIn('empty_str: ""', dumped)
        self.assertIn('with_colon: "foo:bar"', dumped)
        self.assertIn('with_hash: "foo#bar"', dumped)

    def test_roundtrip_complex_structure(self):
        original = {
            "common": {
                "deploy_mode": "cascade",
                "is_cascade": True,
                "custom_ssh_port": 2222,
            },
            "freedom_node": {
                "freedom_host": "192.168.1.100",
                "freedom_port": 22,
                "freedom_user": "root",
                "freedom_xui_version": "1.7.5",
            },
            "proxy_node": {
                "proxy_host": "proxy.example.com",
                "foreign_sub_url": "https://freedom.example.com/subs",
                "proxy_client_tcp_list": "client1,client2",
            }
        }
        dumped = main._dump_yaml_simple(original)
        loaded = main._load_yaml_simple(dumped)
        self.assertEqual(loaded, original)

    def test_roundtrip_idempotency(self):
        sample = {
            "sec_a": {
                "name": "Alpha",
                "count": 10,
                "flag": False,
            },
            "sec_b": {
                "url": "https://test.local:8443/path",
            }
        }
        dump1 = main._dump_yaml_simple(sample)
        loaded1 = main._load_yaml_simple(dump1)
        dump2 = main._dump_yaml_simple(loaded1)
        self.assertEqual(dump1, dump2)

    def test_load_multiline_pipe_block(self):
        yaml_text = (
            "config:\n"
            "  description: |\n"
            "    Line 1\n"
            "    Line 2\n"
            "    Line 3\n"
            "  other: value\n"
        )
        loaded = main._load_yaml_simple(yaml_text)
        self.assertIn("config", loaded)
        self.assertEqual(loaded["config"]["description"], "Line 1\nLine 2\nLine 3")
        self.assertEqual(loaded["config"]["other"], "value")

    def test_load_handles_comments_and_empty_lines(self):
        yaml_text = (
            "# Top level comment\n"
            "\n"
            "section:\n"
            "  # Comment inside section\n"
            "  key: value\n"
            "\n"
            "  number: 123\n"
        )
        loaded = main._load_yaml_simple(yaml_text)
        self.assertEqual(loaded, {"section": {"key": "value", "number": 123}})


class TestBackupConfigSecurity(unittest.TestCase):
    """
    Security verification:
    1. Passwords and private keys (*_key) must never be written to setup_backup.yml.
    2. Even if front-end or malicious input injects sensitive keys, save_backup_config
       must strip them completely.
    3. load_backup_config must strip sensitive keys as a defense-in-depth measure.
    """

    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.tmp_backup_file = os.path.join(self.tmp_dir.name, "setup_backup.yml")
        self.orig_backup_file = main.BACKUP_FILE
        main.BACKUP_FILE = self.tmp_backup_file

    def tearDown(self):
        main.BACKUP_FILE = self.orig_backup_file
        self.tmp_dir.cleanup()

    def test_passwords_and_keys_never_written_to_disk(self):
        test_data = {
            "deploy_mode": "cascade",
            "vps_host": "1.2.3.4",
            "vps_port": 22,
            "vps_user": "root",
            "vps_password": "SuperSecretPassword123!",
            "vps_key": "-----BEGIN OPENSSH PRIVATE KEY-----\nMIIE...\n-----END OPENSSH PRIVATE KEY-----",
            "freedom_host": "5.6.7.8",
            "freedom_password": "FreedomSecretPassword456!",
            "freedom_key": "private_key_content",
            "freedom_xui_password": "PanelPassword789!",
            "proxy_host": "9.10.11.12",
            "proxy_password": "ProxySecretPassword!",
            "proxy_key": "proxy_key_content",
            "proxy_xui_password": "ProxyPanelPassword!",
            "sub_vps_password": "SubServerPassword!",
            "sub_vps_key": "sub_key_content",
            "backup_vps_password": "BackupServerPassword!",
            "backup_vps_key": "backup_key_content",
            "recovery_vps_password": "RecoveryServerPassword!",
            "recovery_vps_key": "recovery_key_content",
            "update_vps_password": "UpdateServerPassword!",
            "update_vps_key": "update_key_content",
            "xui_password": "GenericXuiPassword!",
            "injected_custom_password": "ShouldNeverBeSaved!",
            "injected_ssh_key": "ShouldNeverBeSavedKey!",
        }

        success = main.save_backup_config(test_data)
        self.assertTrue(success, "save_backup_config returned False")
        self.assertTrue(os.path.exists(self.tmp_backup_file), "setup_backup.yml was not created")

        with open(self.tmp_backup_file, "r", encoding="utf-8") as f:
            raw_content = f.read()

        # 1. Check raw file contents for prohibited words
        self.assertNotIn("SuperSecretPassword123!", raw_content)
        self.assertNotIn("FreedomSecretPassword456!", raw_content)
        self.assertNotIn("ProxySecretPassword!", raw_content)
        self.assertNotIn("SubServerPassword!", raw_content)
        self.assertNotIn("PanelPassword789!", raw_content)
        self.assertNotIn("BEGIN OPENSSH PRIVATE KEY", raw_content)
        self.assertNotIn("ShouldNeverBeSaved", raw_content)

        # 2. Check that no key containing 'password' or ending with '_key' exists in the file
        for line in raw_content.splitlines():
            clean_line = line.strip().lower()
            if clean_line.startswith("#") or not clean_line or ":" not in clean_line:
                continue
            key_name = clean_line.split(":", 1)[0].strip()
            self.assertNotIn("password", key_name, f"Forbidden 'password' key found in backup file: {line}")
            self.assertFalse(key_name.endswith("_key"), f"Forbidden '_key' found in backup file: {line}")

        # 3. Load back and verify safe keys are preserved while sensitive are absent
        loaded = main.load_backup_config()
        self.assertEqual(loaded.get("vps_host"), "1.2.3.4")
        self.assertEqual(loaded.get("freedom_host"), "5.6.7.8")
        self.assertEqual(loaded.get("proxy_host"), "9.10.11.12")
        self.assertNotIn("vps_password", loaded)
        self.assertNotIn("vps_key", loaded)
        self.assertNotIn("freedom_password", loaded)
        self.assertNotIn("freedom_key", loaded)

    def test_load_backup_config_strips_sensitive_if_injected(self):
        manual_yaml = (
            "common:\n"
            "  deploy_mode: single\n"
            "injected_section:\n"
            "  admin_password: LeakedPassword!\n"
            "  auth_key: LeakedKey!\n"
            "  safe_value: hello\n"
        )
        with open(self.tmp_backup_file, "w", encoding="utf-8") as f:
            f.write(manual_yaml)

        loaded = main.load_backup_config()
        self.assertEqual(loaded.get("deploy_mode"), "single")
        self.assertEqual(loaded.get("safe_value"), "hello")
        self.assertNotIn("admin_password", loaded)
        self.assertNotIn("auth_key", loaded)


if __name__ == "__main__":
    unittest.main()

