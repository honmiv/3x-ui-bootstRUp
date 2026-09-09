#!/usr/bin/env python3
"""Signature test for main.py public utilities."""

import inspect
import os
import sys
import unittest

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

import main


class TestSigMainPublicUtilities(unittest.TestCase):
    def test_main_public_utilities_signatures(self):
        self.assertEqual(list(inspect.signature(main.fetch_xui_versions).parameters.keys()), [])
        self.assertEqual(list(inspect.signature(main.check_for_update).parameters.keys()), ["force"])
        self.assertEqual(list(inspect.signature(main.list_backup_files).parameters.keys()), ["folder"])


if __name__ == "__main__":
    unittest.main()
