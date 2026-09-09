#!/usr/bin/env python3
"""Unit test for YAML dump/load idempotency."""

import os
import sys
import unittest

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

import main


class TestYamlRoundtripIdempotency(unittest.TestCase):
    def test_roundtrip_idempotency(self):
        sample = {
            "sec_a": {
                "name": "Alpha",
                "count": 10,
                "flag": False,
            },
            "sec_b": {
                "url": "https://test.local:8443/path",
            }
        }
        dump1 = main._dump_yaml_simple(sample)
        loaded1 = main._load_yaml_simple(dump1)
        dump2 = main._dump_yaml_simple(loaded1)
        self.assertEqual(dump1, dump2)


if __name__ == "__main__":
    unittest.main()
