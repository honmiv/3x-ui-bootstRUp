#!/usr/bin/env python3
"""Unit test for MODES_SCHEMA vs STRATEGIES parity."""

import os
import sys
import unittest

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from deployers.strategies import MODES_SCHEMA, STRATEGIES


class TestModesSchemaModesMatchStrategies(unittest.TestCase):
    def test_modes_schema_modes_match_strategies(self):
        schema_modes = set()
        for rule in MODES_SCHEMA:
            for m in rule.get("modes", []):
                schema_modes.add(m)

        strategies_modes = set(STRATEGIES.keys())

        # No dead aliases like 'update'
        self.assertNotIn("update", schema_modes, "Dead mode 'update' must not be in MODES_SCHEMA")

        # Every mode in schema must be a registered strategy
        self.assertEqual(
            schema_modes,
            strategies_modes,
            f"MODES_SCHEMA modes differ from STRATEGIES: schema extra={schema_modes - strategies_modes}, missing={strategies_modes - schema_modes}",
        )


if __name__ == "__main__":
    unittest.main()
