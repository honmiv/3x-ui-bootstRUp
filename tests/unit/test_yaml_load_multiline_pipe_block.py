#!/usr/bin/env python3
"""Unit test for loading multiline pipe (|) blocks in YAML."""

import os
import sys
import unittest

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

import main


class TestYamlLoadMultilinePipeBlock(unittest.TestCase):
    def test_load_multiline_pipe_block(self):
        yaml_text = (
            "config:\n"
            "  description: |\n"
            "    Line 1\n"
            "    Line 2\n"
            "    Line 3\n"
            "  other: value\n"
        )
        loaded = main._load_yaml_simple(yaml_text)
        self.assertIn("config", loaded)
        self.assertEqual(loaded["config"]["description"], "Line 1\nLine 2\nLine 3")
        self.assertEqual(loaded["config"]["other"], "value")


if __name__ == "__main__":
    unittest.main()
