#!/usr/bin/env python3
"""Unit test for changelog diff when new version is prepended at top."""

import importlib.util
import os
import sys
import unittest

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)


class TestChangelogPrependedAtTop(unittest.TestCase):
    def setUp(self):
        spec = importlib.util.spec_from_file_location(
            "main_mod", os.path.join(REPO_ROOT, "main.py")
        )
        self.main_mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.main_mod)

    def test_new_version_prepended_at_top(self):
        local = b"# [1.0.0]\n- Old feature\n"
        remote = (
            b"# [1.1.0]\n"
            b"- New feature A\n"
            b"- Bug fix B\n\n"
            b"# [1.0.0]\n"
            b"- Old feature\n"
        )
        diff = self.main_mod._compute_changelog_diff(local, remote)
        expected = "# [1.1.0]\n- New feature A\n- Bug fix B"
        self.assertEqual(diff, expected)


if __name__ == "__main__":
    unittest.main()
