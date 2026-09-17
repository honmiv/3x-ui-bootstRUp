#!/usr/bin/env python3
"""Unit test verifying update_sub preserves deployed decoy unless new template selected."""

import os
import sys
import unittest

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)


class TestDecoyUpdateSubPreserves(unittest.TestCase):
    def test_update_sub_preserves_decoy_unless_new_template_selected(self):
        repo_root = REPO_ROOT

        with open(os.path.join(repo_root, "sub-server", "setup.sh"), encoding="utf-8") as f:
            setup_sh = f.read()
        self.assertIn("UPDATE_SUB_DECOY", setup_sh)
        self.assertIn("DECOY_HTML_BACKUP", setup_sh)
        self.assertIn('rm -rf ./working/nginx-decoy/html', setup_sh)
        self.assertIn('cp -r "$DECOY_HTML_BACKUP" ./working/nginx-decoy/html', setup_sh)

        with open(os.path.join(repo_root, "deployers", "maintenance.py"), encoding="utf-8") as f:
            maintenance = f.read()
        self.assertIn('sub_env["UPDATE_SUB_DECOY"] = "1"', maintenance)
        self.assertIn("update_sub_decoy_files is not None", maintenance)


if __name__ == "__main__":
    unittest.main()
