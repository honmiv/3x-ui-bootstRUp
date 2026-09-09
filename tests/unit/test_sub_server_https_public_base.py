#!/usr/bin/env python3
"""Unit test: Sub-server _public_base defaults to https."""

import importlib.util
import os
import sys
import unittest

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)


class TestSubServerHttpsPublicBase(unittest.TestCase):
    def setUp(self):
        spec = importlib.util.spec_from_file_location(
            "sub_server_mod", os.path.join(REPO_ROOT, "sub-server", "server.py")
        )
        self.sub_mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.sub_mod)

    def test_public_base_defaults_to_https(self):
        handler = self.sub_mod.Handler.__new__(self.sub_mod.Handler)
        handler.headers = {"Host": "sub.example.com"}
        self.assertEqual(handler._public_base(), "https://sub.example.com")


if __name__ == "__main__":
    unittest.main()
