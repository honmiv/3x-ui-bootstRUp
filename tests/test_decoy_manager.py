import hashlib
import io
import os
import re
import shutil
import tarfile
import tempfile
import unittest
from unittest.mock import patch

import decoy_manager
from ssh_deployer import get_bundle_bytes


class TestDecoyManager(unittest.TestCase):
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

            # Check content of index.html
            extracted = tar.extractfile("common/templates/nginx-decoy/html/index.html").read()
            self.assertEqual(extracted, custom_decoy["index.html"])

    def test_mock_download_and_cache(self):
        # Create a mock tar.gz archive in memory
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
                    # Check errors merged
                    self.assertTrue(os.path.isdir(os.path.join(cached_dir, "errors")))
                    self.assertTrue(os.path.isfile(os.path.join(cached_dir, "errors", "404.html")))

                    files = decoy_manager.get_decoy_bundle_files("game-2048", randomize=True)
                    self.assertIn("index.html", files)
                    self.assertIn("errors/404.html", files)
                finally:
                    decoy_manager.CACHE_DIR = original_cache

    def test_update_sub_preserves_decoy_unless_new_template_selected(self):
        repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

        # A bare update_sub must never reset the deployed decoy back to the
        # builtin documentation site. The remote script has to back up the
        # live decoy before regenerating ./working and restore it afterwards,
        # unless the orchestrator explicitly requested a new template.
        with open(os.path.join(repo_root, "sub-server", "setup.sh"), encoding="utf-8") as f:
            setup_sh = f.read()
        self.assertIn("UPDATE_SUB_DECOY", setup_sh)
        self.assertIn("DECOY_HTML_BACKUP", setup_sh)
        self.assertIn('rm -rf ./working/nginx-decoy/html', setup_sh)
        self.assertIn('cp -r "$DECOY_HTML_BACKUP" ./working/nginx-decoy/html', setup_sh)

        # The orchestrator marks an update as "apply a new decoy" only when a
        # template was actually selected; otherwise the preserve path runs.
        with open(os.path.join(repo_root, "ssh_deployer.py"), encoding="utf-8") as f:
            ssh_deployer = f.read()
        self.assertIn('sub_env["UPDATE_SUB_DECOY"] = "1"', ssh_deployer)
        self.assertIn("update_sub_decoy_files is not None", ssh_deployer)


if __name__ == "__main__":
    unittest.main()
