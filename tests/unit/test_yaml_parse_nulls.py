#!/usr/bin/env python3
"""Unit test for _parse_yaml_scalar null parsing."""

import os
import sys
import unittest

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

import main


class TestYamlParseNulls(unittest.TestCase):
    def test_parse_nulls(self):
        for raw in ["null", "Null", "NULL", "none", "None", "~"]:
            self.assertIsNone(main._parse_yaml_scalar(raw), f"Failed for {raw}")


if __name__ == "__main__":
    unittest.main()
