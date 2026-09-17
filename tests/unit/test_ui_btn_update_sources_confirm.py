#!/usr/bin/env python3
"""UI JS logic test: btnUpdateSources uses custom showConfirm and showAlert."""

import os
import sys
import unittest

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)


class TestUiBtnUpdateSourcesConfirm(unittest.TestCase):
    def test_btn_update_sources_uses_custom_confirm_and_alert(self):
        with open(os.path.join(REPO_ROOT, "panel", "static", "app.js"), "r", encoding="utf-8") as f:
            app_js = f.read()
        self.assertIn("btnUpdateSources.addEventListener('click'", app_js)
        self.assertIn("showConfirm(", app_js)
        self.assertIn("Обновление деплоера", app_js)
        self.assertIn("showAlert(", app_js)


if __name__ == "__main__":
    unittest.main()
