#!/usr/bin/env python3
"""Signature test for main.py YAML utility functions."""

import inspect
import os
import sys
import unittest

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

import main


class TestSigMainYaml(unittest.TestCase):
    def test_main_yaml_signatures(self):
        self.assertEqual(list(inspect.signature(main._dump_yaml_simple).parameters.keys()), ["data"])
        self.assertEqual(list(inspect.signature(main._load_yaml_simple).parameters.keys()), ["text"])
        self.assertEqual(list(inspect.signature(main._parse_yaml_scalar).parameters.keys()), ["val_str"])


if __name__ == "__main__":
    unittest.main()
