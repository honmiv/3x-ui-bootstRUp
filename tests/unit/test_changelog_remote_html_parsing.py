#!/usr/bin/env python3
"""Unit test for parsing remote HTML banner files."""

import importlib.util
import os
import sys
import unittest

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)


class TestChangelogRemoteHtmlParsing(unittest.TestCase):
    def setUp(self):
        spec = importlib.util.spec_from_file_location(
            "main_mod", os.path.join(REPO_ROOT, "main.py")
        )
        self.main_mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.main_mod)

    def test_remote_html_parsing(self):
        remote_files = {
            "notification.html": b'<span class="warning-icon">!</span><span>HTML announcement</span>',
            "update_banner.html": b'<span>Custom update banner</span>',
        }
        res_notif = self.main_mod._parse_remote_html(remote_files, "notification.html")
        res_update = self.main_mod._parse_remote_html(remote_files, "update_banner.html")
        self.assertIn("HTML announcement", res_notif)
        self.assertIn("Custom update banner", res_update)


if __name__ == "__main__":
    unittest.main()
