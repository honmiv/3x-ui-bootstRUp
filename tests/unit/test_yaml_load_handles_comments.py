#!/usr/bin/env python3
"""Unit test for loading YAML with comments and blank lines."""

import os
import sys
import unittest

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

import main


class TestYamlLoadHandlesComments(unittest.TestCase):
    def test_load_handles_comments_and_empty_lines(self):
        yaml_text = (
            "# Top level comment\n"
            "\n"
            "section:\n"
            "  # Comment inside section\n"
            "  key: value\n"
            "\n"
            "  number: 123\n"
        )
        loaded = main._load_yaml_simple(yaml_text)
        self.assertEqual(loaded, {"section": {"key": "value", "number": 123}})


if __name__ == "__main__":
    unittest.main()
