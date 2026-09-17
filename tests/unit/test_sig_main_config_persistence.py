#!/usr/bin/env python3
"""Signature test for main.py config persistence functions."""

import inspect
import os
import sys
import unittest

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

import main


class TestSigMainConfigPersistence(unittest.TestCase):
    def test_main_config_persistence_signatures(self):
        self.assertEqual(list(inspect.signature(main.save_backup_config).parameters.keys()), ["data"])
        self.assertEqual(list(inspect.signature(main.load_backup_config).parameters.keys()), [])


if __name__ == "__main__":
    unittest.main()
