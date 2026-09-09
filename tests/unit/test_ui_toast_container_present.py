#!/usr/bin/env python3
"""UI structure test for toast container in index.html."""

import os
import sys
import unittest

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)


class TestUiToastContainerPresent(unittest.TestCase):
    def test_toast_container_present_in_index_html(self):
        with open(os.path.join(REPO_ROOT, "panel", "static", "index.html"), "r", encoding="utf-8") as f:
            html = f.read()
        self.assertIn('id="toastContainer"', html)


if __name__ == "__main__":
    unittest.main()
