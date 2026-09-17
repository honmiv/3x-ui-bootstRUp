#!/usr/bin/env python3
"""Unit test for builtin decoy files and anti-fingerprint randomization."""

import hashlib
import os
import re
import sys
import unittest

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

import decoy_manager


class TestDecoyBuiltinRandomization(unittest.TestCase):
    def test_builtin_files_and_anti_fingerprint_randomization(self):
        files1 = decoy_manager.get_decoy_bundle_files("builtin", randomize=True)
        self.assertIn("index.html", files1)
        self.assertIn("errors/404.html", files1)

        html1 = files1["index.html"].decode("utf-8")
        match = re.search(r"<!-- ([\x20-\x7e]+) -->", html1)
        self.assertIsNotNone(match, "expected a bare printable-ASCII nonce comment in index.html")
        self.assertGreaterEqual(len(match.group(1)), 20)
        self.assertLessEqual(len(match.group(1)), 64)
        self.assertNotIn("--", match.group(1))

        files2 = decoy_manager.get_decoy_bundle_files("builtin", randomize=True)
        html2 = files2["index.html"].decode("utf-8")

        # Each run produces a unique randomized nonce tag
        self.assertNotEqual(files1["index.html"], files2["index.html"])
        hash1 = hashlib.sha256(files1["index.html"]).hexdigest()
        hash2 = hashlib.sha256(files2["index.html"]).hexdigest()
        self.assertNotEqual(hash1, hash2)


if __name__ == "__main__":
    unittest.main()
