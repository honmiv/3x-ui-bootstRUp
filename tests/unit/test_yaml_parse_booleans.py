#!/usr/bin/env python3
"""Unit test for _parse_yaml_scalar boolean parsing."""

import os
import sys
import unittest

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

import main


class TestYamlParseBooleans(unittest.TestCase):
    def test_parse_booleans(self):
        for raw, expected in [
            ("true", True), ("True", True), ("TRUE", True),
            ("yes", True), ("Yes", True), ("on", True),
            ("false", False), ("False", False), ("FALSE", False),
            ("no", False), ("No", False), ("off", False),
        ]:
            self.assertEqual(main._parse_yaml_scalar(raw), expected, f"Failed for {raw}")


if __name__ == "__main__":
    unittest.main()
