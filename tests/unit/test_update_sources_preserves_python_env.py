#!/usr/bin/env python3
"""Unit test verifying update_sources scripts preserve portable .python_env."""

import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
import unittest

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)


class TestUpdateSourcesPreservesPythonEnv(unittest.TestCase):
    def test_preserve_lists_include_python_env(self):
        with open(os.path.join(REPO_ROOT, "update_sources.sh"), encoding="utf-8") as f:
            update_sh = f.read()
        self.assertIn('"$name" == ".python_env"', update_sh)

        with open(os.path.join(REPO_ROOT, "update_sources.ps1"), encoding="utf-8") as f:
            update_ps1 = f.read()
        self.assertIn("'.python_env'", update_ps1)

        with open(os.path.join(REPO_ROOT, "start_3x_ui_deployment_manager.sh"), encoding="utf-8") as f:
            start_sh = f.read()
        self.assertIn('ENV_DIR="$SCRIPT_DIR/.python_env"', start_sh)

    @unittest.skipUnless(
        os.name == "posix" and all(shutil.which(c) for c in ("bash", "curl", "tar")),
        "Requires POSIX bash, curl, and tar",
    )
    def test_update_sources_sh_preserves_portable_python(self):
        with tempfile.TemporaryDirectory() as tmp:
            src_root = os.path.join(tmp, "src", "3x-ui-bootstRUp-master")
            target_dir = os.path.join(tmp, "target")
            py_bin_dir = os.path.join(target_dir, ".python_env", "bin")
            os.makedirs(src_root)
            os.makedirs(py_bin_dir)

            mock_py = os.path.join(py_bin_dir, "python3")
            with open(mock_py, "w", encoding="utf-8") as f:
                f.write("#!/usr/bin/env bash\necho \"PORTABLE_PY:$*\"\n")
            os.chmod(mock_py, 0o755)

            marker_path = os.path.join(target_dir, ".python_env", "marker.txt")
            with open(marker_path, "w", encoding="utf-8") as f:
                f.write("keep")

            obsolete_path = os.path.join(target_dir, "obsolete.txt")
            with open(obsolete_path, "w", encoding="utf-8") as f:
                f.write("remove")

            for fname in ("update_sources.sh", "start_3x_ui_deployment_manager.sh"):
                shutil.copy2(os.path.join(REPO_ROOT, fname), os.path.join(target_dir, fname))
                shutil.copy2(os.path.join(REPO_ROOT, fname), os.path.join(src_root, fname))

            with open(os.path.join(src_root, "main.py"), "w", encoding="utf-8") as f:
                f.write('print("updated")\n')

            archive_path = os.path.join(tmp, "archive.tar.gz")
            with tarfile.open(archive_path, "w:gz") as tf:
                tf.add(src_root, arcname="3x-ui-bootstRUp-master")

            env = os.environ.copy()
            env["TARGET_DIR"] = target_dir
            env["ARCHIVE_URL"] = f"file://{archive_path}"

            proc = subprocess.run(
                ["bash", os.path.join(target_dir, "update_sources.sh")],
                capture_output=True,
                text=True,
                env=env,
                check=False,
            )
            self.assertEqual(proc.returncode, 0, msg=proc.stdout + proc.stderr)
            self.assertTrue(os.path.isfile(marker_path))
            self.assertFalse(os.path.exists(obsolete_path))
            self.assertIn("[KEEP] .python_env", proc.stdout)
            self.assertIn("PORTABLE_PY:main.py", proc.stdout)
            self.assertNotIn("Downloading isolated runtime", proc.stdout)


if __name__ == "__main__":
    unittest.main()
