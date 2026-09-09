#!/usr/bin/env python3
"""Unit test for MODES_SCHEMA structural validity."""

import os
import sys
import unittest

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from deployers.strategies import MODES_SCHEMA


class TestSchemaRuleStructures(unittest.TestCase):
    def test_schema_rule_structures(self):
        for idx, rule in enumerate(MODES_SCHEMA):
            kind = rule.get("kind")
            self.assertIn(kind, ("field", "group"), f"Rule #{idx} has invalid kind: {kind}")

            modes = rule.get("modes")
            self.assertIsInstance(modes, list, f"Rule #{idx} modes must be a list")
            self.assertTrue(len(modes) > 0, f"Rule #{idx} modes list must not be empty")

            if kind == "field":
                fid = rule.get("id")
                self.assertTrue(bool(fid and isinstance(fid, str)), f"Rule #{idx} missing valid 'id'")
            elif kind == "group":
                fields = rule.get("fields")
                self.assertIsInstance(fields, list, f"Rule #{idx} 'fields' must be a list")
                self.assertTrue(len(fields) > 1, f"Rule #{idx} 'group' should contain at least 2 fields")


if __name__ == "__main__":
    unittest.main()
