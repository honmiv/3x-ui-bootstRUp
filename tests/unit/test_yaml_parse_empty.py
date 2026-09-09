#!/usr/bin/env python3
"""Unit test for _parse_yaml_scalar empty and whitespace strings."""

import os
import sys
import unittest

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

import main


class TestYamlParseEmpty(unittest.TestCase):
    def test_parse_empty(self):
        self.assertEqual(main._parse_yaml_scalar(""), "")
        self.assertEqual(main._parse_yaml_scalar("   "), "")


if __name__ == "__main__":
    unittest.main()
