#!/usr/bin/env python3
"""UI structure test for custom confirm modal in index.html."""

import os
import sys
import unittest

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)


class TestUiCustomConfirmModalPresent(unittest.TestCase):
    def test_custom_confirm_modal_present_in_index_html(self):
        with open(os.path.join(REPO_ROOT, "panel", "static", "index.html"), "r", encoding="utf-8") as f:
            html = f.read()
        self.assertIn('id="customConfirmModal"', html)
        self.assertIn('id="customModalTitle"', html)
        self.assertIn('id="customModalMessage"', html)
        self.assertIn('id="customModalIconWrapper"', html)
        self.assertIn('id="customModalIcon"', html)
        self.assertIn('id="customModalConfirmBtn"', html)
        self.assertIn('id="customModalCancelBtn"', html)


if __name__ == "__main__":
    unittest.main()
