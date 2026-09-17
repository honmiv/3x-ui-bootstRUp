#!/usr/bin/env python3
"""Unit test for decoy catalog structure and contents."""

import os
import sys
import unittest

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

import decoy_manager


class TestDecoyCatalogStructure(unittest.TestCase):
    def test_catalog_structure(self):
        catalog = decoy_manager.get_decoy_catalog()
        self.assertGreaterEqual(len(catalog), 21)
        ids = [item["id"] for item in catalog]
        self.assertIn("builtin", ids)
        self.assertIn("game-2048", ids)
        self.assertIn("game-hextris", ids)
        self.assertIn("agency-landing", ids)
        self.assertIn("landing-page", ids)
        self.assertIn("creative", ids)
        self.assertIn("new-age", ids)
        self.assertIn("business-casual", ids)
        self.assertIn("clean-blog", ids)
        self.assertIn("freelancer-portfolio", ids)
        self.assertIn("stylish-portfolio", ids)
        self.assertIn("coming-soon", ids)
        self.assertIn("resume", ids)

        builtin = next(item for item in catalog if item["id"] == "builtin")
        self.assertTrue(builtin["is_cached"])


if __name__ == "__main__":
    unittest.main()
