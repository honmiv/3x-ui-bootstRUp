#!/usr/bin/env python3
"""Unit test for arbitrary line diff fallback in changelog."""

import importlib.util
import os
import sys
import unittest

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)


class TestChangelogArbitraryDiff(unittest.TestCase):
    def setUp(self):
        spec = importlib.util.spec_from_file_location(
            "main_mod", os.path.join(REPO_ROOT, "main.py")
        )
        self.main_mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.main_mod)

    def test_arbitrary_line_diff_fallback(self):
        local = b"- Line 1\n- Line 2\n"
        remote = b"- Line 1\n- Line 1.5 modified\n- Line 2\n"
        diff = self.main_mod._compute_changelog_diff(local, remote)
        self.assertIn("Line 1.5 modified", diff)


if __name__ == "__main__":
    unittest.main()
