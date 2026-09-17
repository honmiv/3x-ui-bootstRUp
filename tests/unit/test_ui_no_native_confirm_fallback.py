#!/usr/bin/env python3
"""UI JS logic test: ensure no native confirm/alert bypass exists."""

import os
import re
import sys
import unittest

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)


class TestUiNoNativeConfirmFallback(unittest.TestCase):
    def test_no_native_confirm_fallback_in_show_confirm(self):
        with open(os.path.join(REPO_ROOT, "panel", "static", "app.js"), "r", encoding="utf-8") as f:
            app_js = f.read()
        ui_js_path = os.path.join(REPO_ROOT, "panel", "static", "modules", "ui.js")
        ui_js = ""
        if os.path.exists(ui_js_path):
            with open(ui_js_path, "r", encoding="utf-8") as f:
                ui_js = f.read()

        js_code = ui_js + "\n" + app_js
        show_confirm_match = re.search(r"function showConfirm\s*\(.*?\)\s*\{(.*?)\n\}", js_code, re.DOTALL)
        self.assertIsNotNone(show_confirm_match)
        body = show_confirm_match.group(1)
        self.assertNotIn("window.nativeConfirm", body)
        self.assertNotIn("nativeAlert", js_code)


if __name__ == "__main__":
    unittest.main()
