#!/usr/bin/env python3
"""UI JS logic test: btnShutdown uses custom showConfirm with danger styling."""

import os
import sys
import unittest

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)


class TestUiBtnShutdownConfirm(unittest.TestCase):
    def test_btn_shutdown_uses_custom_confirm_with_danger(self):
        with open(os.path.join(REPO_ROOT, "panel", "static", "app.js"), "r", encoding="utf-8") as f:
            app_js = f.read()
        self.assertIn("btnShutdown.addEventListener('click'", app_js)
        self.assertIn("Выключение сервера", app_js)
        self.assertIn("danger: true", app_js)


if __name__ == "__main__":
    unittest.main()
