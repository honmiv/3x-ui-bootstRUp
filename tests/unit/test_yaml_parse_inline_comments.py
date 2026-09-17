#!/usr/bin/env python3
"""Unit test for _parse_yaml_scalar inline comment stripping."""

import os
import sys
import unittest

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

import main


class TestYamlParseInlineComments(unittest.TestCase):
    def test_parse_inline_comments(self):
        self.assertEqual(main._parse_yaml_scalar("example.com # server domain"), "example.com")
        self.assertEqual(main._parse_yaml_scalar("8080 # port"), 8080)
        self.assertEqual(main._parse_yaml_scalar("true # enable feature"), True)


if __name__ == "__main__":
    unittest.main()
