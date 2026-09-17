#!/usr/bin/env python3
"""Unit test for bundle integration with decoy files."""

import io
import os
import sys
import tarfile
import unittest

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from ssh_deployer import get_bundle_bytes


class TestDecoyBundleIntegration(unittest.TestCase):
    def test_bundle_integration_with_decoy_files(self):
        custom_decoy = {
            "index.html": b"<!DOCTYPE html><html><body><h1>Custom Decoy Test</h1></body></html>",
            "style.css": b"body { background: black; }",
            "errors/404.html": b"<h1>404</h1>"
        }

        bundle_bytes = get_bundle_bytes(decoy_files=custom_decoy)
        with tarfile.open(fileobj=io.BytesIO(bundle_bytes), mode="r:gz") as tar:
            names = tar.getnames()
            self.assertIn("common/templates/nginx-decoy/html/index.html", names)
            self.assertIn("common/templates/nginx-decoy/html/style.css", names)
            self.assertIn("common/templates/nginx-decoy/html/errors/404.html", names)

            extracted = tar.extractfile("common/templates/nginx-decoy/html/index.html").read()
            self.assertEqual(extracted, custom_decoy["index.html"])


if __name__ == "__main__":
    unittest.main()
