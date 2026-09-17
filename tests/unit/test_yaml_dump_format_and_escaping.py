#!/usr/bin/env python3
"""Unit test for _dump_yaml_simple formatting and escaping."""

import os
import sys
import unittest

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

import main


class TestYamlDumpFormatAndEscaping(unittest.TestCase):
    def test_dump_format_and_escaping(self):
        data = {
            "section1": {
                "host": "example.com",
                "port": 443,
                "enabled": True,
                "disabled": False,
                "empty_str": "",
                "with_colon": "foo:bar",
                "with_hash": "foo#bar",
            }
        }
        dumped = main._dump_yaml_simple(data)
        self.assertIn("section1:", dumped)
        self.assertIn("host: example.com", dumped)
        self.assertIn("port: 443", dumped)
        self.assertIn("enabled: true", dumped)
        self.assertIn("disabled: false", dumped)
        self.assertIn('empty_str: ""', dumped)
        self.assertIn('with_colon: "foo:bar"', dumped)
        self.assertIn('with_hash: "foo#bar"', dumped)


if __name__ == "__main__":
    unittest.main()
