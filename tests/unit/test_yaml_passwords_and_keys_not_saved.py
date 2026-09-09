#!/usr/bin/env python3
"""Security test: passwords and private keys (*_key) are never persisted to disk."""

import os
import sys
import tempfile
import unittest

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

import main


class TestYamlPasswordsNotSaved(unittest.TestCase):
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

        # Check raw file contents for prohibited words
        self.assertNotIn("SuperSecretPassword123!", raw_content)
        self.assertNotIn("FreedomSecretPassword456!", raw_content)
        self.assertNotIn("ProxySecretPassword!", raw_content)
        self.assertNotIn("SubServerPassword!", raw_content)
        self.assertNotIn("PanelPassword789!", raw_content)
        self.assertNotIn("BEGIN OPENSSH PRIVATE KEY", raw_content)
        self.assertNotIn("ShouldNeverBeSaved", raw_content)

        # Check that no key containing 'password' or ending with '_key' exists in the file
        for line in raw_content.splitlines():
            clean_line = line.strip().lower()
            if clean_line.startswith("#") or not clean_line or ":" not in clean_line:
                continue
            key_name = clean_line.split(":", 1)[0].strip()
            self.assertNotIn("password", key_name, f"Forbidden 'password' key found in backup file: {line}")
            self.assertFalse(key_name.endswith("_key"), f"Forbidden '_key' found in backup file: {line}")

        # Load back and verify safe keys are preserved while sensitive are absent
        loaded = main.load_backup_config()
        self.assertEqual(loaded.get("vps_host"), "1.2.3.4")
        self.assertEqual(loaded.get("freedom_host"), "5.6.7.8")
        self.assertEqual(loaded.get("proxy_host"), "9.10.11.12")
        self.assertNotIn("vps_password", loaded)
        self.assertNotIn("vps_key", loaded)
        self.assertNotIn("freedom_password", loaded)
        self.assertNotIn("freedom_key", loaded)


if __name__ == "__main__":
    unittest.main()
