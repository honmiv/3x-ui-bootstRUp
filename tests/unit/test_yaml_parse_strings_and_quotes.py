#!/usr/bin/env python3
"""Unit test for _parse_yaml_scalar string and quote parsing."""

import os
import sys
import unittest

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

import main


class TestYamlParseStringsAndQuotes(unittest.TestCase):
    def test_parse_strings_and_quotes(self):
        self.assertEqual(main._parse_yaml_scalar('"hello world"'), "hello world")
        self.assertEqual(main._parse_yaml_scalar("'simple string'"), "simple string")
        self.assertEqual(main._parse_yaml_scalar('"line1\\nline2"'), "line1\nline2")
        self.assertEqual(main._parse_yaml_scalar('"escaped \\"quotes\\""'), 'escaped "quotes"')
        self.assertEqual(main._parse_yaml_scalar('"tab\\there"'), "tab\there")
        self.assertEqual(main._parse_yaml_scalar("'it''s fine'"), "it's fine")


if __name__ == "__main__":
    unittest.main()
