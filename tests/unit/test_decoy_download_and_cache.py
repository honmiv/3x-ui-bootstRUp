#!/usr/bin/env python3
"""Unit test for decoy mock download and caching."""

import io
import os
import sys
import tarfile
import tempfile
import unittest
from unittest.mock import patch

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

import decoy_manager


class TestDecoyDownloadAndCache(unittest.TestCase):
    def test_mock_download_and_cache(self):
        archive_buf = io.BytesIO()
        with tarfile.open(fileobj=archive_buf, mode="w:gz") as tar:
            content = b"<html><head><title>Mock Game</title></head><body>Play</body></html>"
            ti = tarfile.TarInfo(name="mock-repo-master/index.html")
            ti.size = len(content)
            tar.addfile(ti, io.BytesIO(content))

        archive_bytes = archive_buf.getvalue()

        with patch("decoy_manager._fetch_archive_bytes", return_value=archive_bytes):
            with tempfile.TemporaryDirectory() as tmp_dir:
                original_cache = decoy_manager.CACHE_DIR
                decoy_manager.CACHE_DIR = tmp_dir
                try:
                    cached_dir = decoy_manager.ensure_decoy_cached("game-2048", force=True)
                    self.assertTrue(os.path.isdir(cached_dir))
                    self.assertTrue(os.path.isfile(os.path.join(cached_dir, "index.html")))
                    self.assertTrue(os.path.isdir(os.path.join(cached_dir, "errors")))
                    self.assertTrue(os.path.isfile(os.path.join(cached_dir, "errors", "404.html")))

                    files = decoy_manager.get_decoy_bundle_files("game-2048", randomize=True)
                    self.assertIn("index.html", files)
                    self.assertIn("errors/404.html", files)
                finally:
                    decoy_manager.CACHE_DIR = original_cache


if __name__ == "__main__":
    unittest.main()
