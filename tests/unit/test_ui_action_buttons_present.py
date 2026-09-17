#!/usr/bin/env python3
"""UI structure test for action buttons in index.html."""

import os
import sys
import unittest

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)


class TestUiActionButtonsPresent(unittest.TestCase):
    def test_action_buttons_present_in_index_html(self):
        with open(os.path.join(REPO_ROOT, "panel", "static", "index.html"), "r", encoding="utf-8") as f:
            html = f.read()
        self.assertIn('id="btnUpdateSources"', html)
        self.assertIn('id="btnRestart"', html)
        self.assertIn('id="btnShutdown"', html)


if __name__ == "__main__":
    unittest.main()
