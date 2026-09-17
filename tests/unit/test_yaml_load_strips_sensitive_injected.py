#!/usr/bin/env python3
"""Security test: load_backup_config strips sensitive keys even if directly injected in YAML."""

import os
import sys
import tempfile
import unittest

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

import main


class TestYamlLoadStripsSensitiveInjected(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.tmp_backup_file = os.path.join(self.tmp_dir.name, "setup_backup.yml")
        self.orig_backup_file = main.BACKUP_FILE
        main.BACKUP_FILE = self.tmp_backup_file

    def tearDown(self):
        main.BACKUP_FILE = self.orig_backup_file
        self.tmp_dir.cleanup()

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
