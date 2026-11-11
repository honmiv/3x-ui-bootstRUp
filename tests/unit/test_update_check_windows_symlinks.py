#!/usr/bin/env python3
"""Unit tests for update check consistency across Windows ZIP/git checkouts and symlinks."""

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

import main


class _FakeResponse:
    def __init__(self, payload: bytes):
        self._payload = payload

    def read(self) -> bytes:
        return self._payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


def _build_tar_gz(files, symlinks) -> bytes:
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tf:
        for rel, content in files.items():
            info = tarfile.TarInfo(name=f"3x-ui-bootstRUp-master/{rel}")
            info.size = len(content)
            info.type = tarfile.REGTYPE
            tf.addfile(info, io.BytesIO(content))
        for rel, target in symlinks.items():
            info = tarfile.TarInfo(name=f"3x-ui-bootstRUp-master/{rel}")
            info.type = tarfile.SYMTYPE
            info.linkname = target
            tf.addfile(info)
    return buf.getvalue()


def _write_local_tree(root: str, files) -> None:
    for rel, content in files.items():
        path = os.path.join(root, *rel.split("/"))
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "wb") as f:
            f.write(content)


class TestUpdateCheckWindowsSymlinks(unittest.TestCase):
    def setUp(self):
        self.remote_files = {
            "AGENTS.md": b"# Guide\nLine 2\n",
            "main.py": b"print('ok')\n",
            "change.log": b"# Changelog\n- Init\n",
        }
        self.remote_symlinks = {
            "SKILL.md": "AGENTS.md",
            ".github/copilot-instructions.md": "../AGENTS.md",
        }
        self.tar_bytes = _build_tar_gz(self.remote_files, self.remote_symlinks)

    def _run_check(self, local_files, tar_bytes=None):
        payload = tar_bytes if tar_bytes is not None else self.tar_bytes
        with tempfile.TemporaryDirectory() as tmp_dir:
            _write_local_tree(tmp_dir, local_files)
            with patch.object(main, "APP_DIR", tmp_dir), \
                 patch.object(main.urllib.request, "urlopen", return_value=_FakeResponse(payload)):
                return main.check_for_update(force=True)

    def test_zip_extracted_symlink_stubs_match_remote_tar(self):
        """Windows Expand-Archive turns git symlinks into plain text files containing the target path."""
        local_files = dict(self.remote_files)
        local_files["SKILL.md"] = b"AGENTS.md"
        local_files[".github/copilot-instructions.md"] = b"../AGENTS.md"

        res = self._run_check(local_files)
        self.assertFalse(res["update_available"])
        self.assertEqual(res["local_version"], res["latest_version"])
        self.assertEqual(res["files"], {"local": 3, "remote": 3})

    def test_crlf_line_endings_and_symlink_stubs_match_remote_tar(self):
        """Windows git clone with core.autocrlf=true matches upstream LF tarball."""
        local_files = {
            "AGENTS.md": b"# Guide\r\nLine 2\r\n",
            "main.py": b"print('ok')\r\n",
            "change.log": b"# Changelog\r\n- Init\r\n",
            "SKILL.md": b"AGENTS.md\r\n",
            ".github/copilot-instructions.md": b"../AGENTS.md",
        }

        res = self._run_check(local_files)
        self.assertFalse(res["update_available"])
        self.assertEqual(res["local_version"], res["latest_version"])

    def test_dereferenced_symlink_copies_match_remote_tar(self):
        """Extractors that copy symlink target contents still match upstream symlinks."""
        local_files = dict(self.remote_files)
        local_files["SKILL.md"] = self.remote_files["AGENTS.md"]
        local_files[".github/copilot-instructions.md"] = self.remote_files["AGENTS.md"]

        res = self._run_check(local_files)
        self.assertFalse(res["update_available"])

    def test_windows_os_metadata_files_ignored(self):
        """Windows/macOS desktop metadata files do not trigger false update alerts."""
        local_files = dict(self.remote_files)
        local_files["SKILL.md"] = b"AGENTS.md"
        local_files[".github/copilot-instructions.md"] = b"../AGENTS.md"
        local_files["Thumbs.db"] = b"fake thumbs"
        local_files["desktop.ini"] = b"[.ShellClassInfo]\r\n"
        local_files[".DS_Store"] = b"mac meta"

        res = self._run_check(local_files)
        self.assertFalse(res["update_available"])

    def test_real_code_change_still_triggers_update(self):
        """Modified code file still sets update_available=True."""
        local_files = dict(self.remote_files)
        local_files["SKILL.md"] = b"AGENTS.md"
        local_files[".github/copilot-instructions.md"] = b"../AGENTS.md"
        local_files["main.py"] = b"print('old')\n"

        res = self._run_check(local_files)
        self.assertTrue(res["update_available"])

    def test_symlink_target_change_still_triggers_update(self):
        """If upstream symlink points to a different target, update is still detected."""
        local_files = dict(self.remote_files)
        local_files["SKILL.md"] = b"OLD_DOC.md"
        local_files[".github/copilot-instructions.md"] = b"../AGENTS.md"

        res = self._run_check(local_files)
        self.assertTrue(res["update_available"])


if __name__ == "__main__":
    unittest.main()
