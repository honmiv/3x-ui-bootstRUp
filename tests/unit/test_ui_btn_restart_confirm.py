#!/usr/bin/env python3
"""UI JS logic test: btnRestart uses custom showConfirm."""

import os
import sys
import unittest

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)


class TestUiBtnRestartConfirm(unittest.TestCase):
    def test_btn_restart_uses_custom_confirm(self):
        with open(os.path.join(REPO_ROOT, "panel", "static", "app.js"), "r", encoding="utf-8") as f:
            app_js = f.read()
        self.assertIn("btnRestart.addEventListener('click'", app_js)
        self.assertIn("Перезапуск сервера", app_js)


if __name__ == "__main__":
    unittest.main()
