#!/usr/bin/env python3
"""Unit test for changelog diff with identical local and remote."""

import importlib.util
import os
import sys
import unittest

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)


class TestChangelogIdentical(unittest.TestCase):
    def setUp(self):
        spec = importlib.util.spec_from_file_location(
            "main_mod", os.path.join(REPO_ROOT, "main.py")
        )
        self.main_mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.main_mod)

    def test_identical(self):
        local = b"# [1.0.0]\n- Some change\n"
        remote = b"# [1.0.0]\n- Some change\n"
        diff = self.main_mod._compute_changelog_diff(local, remote)
        self.assertEqual(diff, "")


if __name__ == "__main__":
    unittest.main()
