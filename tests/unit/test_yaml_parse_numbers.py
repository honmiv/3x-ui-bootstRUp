#!/usr/bin/env python3
"""Unit test for _parse_yaml_scalar integer and float parsing."""

import os
import sys
import unittest

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

import main


class TestYamlParseNumbers(unittest.TestCase):
    def test_parse_numbers(self):
        self.assertEqual(main._parse_yaml_scalar("42"), 42)
        self.assertEqual(main._parse_yaml_scalar("-10"), -10)
        self.assertEqual(main._parse_yaml_scalar("0"), 0)
        self.assertEqual(main._parse_yaml_scalar("3.14"), 3.14)
        self.assertEqual(main._parse_yaml_scalar("-0.5"), -0.5)


if __name__ == "__main__":
    unittest.main()
