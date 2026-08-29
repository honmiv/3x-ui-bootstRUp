import unittest
import importlib.util
import os

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class TestChangelogDiff(unittest.TestCase):
    def setUp(self):
        spec = importlib.util.spec_from_file_location(
            "main_mod", os.path.join(REPO_ROOT, "main.py")
        )
        self.main_mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.main_mod)

    def test_empty_remote(self):
        local = b"# [1.0.0]\n- Some change\n"
        remote = b""
        diff = self.main_mod._compute_changelog_diff(local, remote)
        self.assertEqual(diff, "")

    def test_empty_local(self):
        local = b""
        remote = b"# [1.0.0]\n- Some change\n"
        diff = self.main_mod._compute_changelog_diff(local, remote)
        self.assertEqual(diff, "# [1.0.0]\n- Some change")

    def test_identical(self):
        local = b"# [1.0.0]\n- Some change\n"
        remote = b"# [1.0.0]\n- Some change\n"
        diff = self.main_mod._compute_changelog_diff(local, remote)
        self.assertEqual(diff, "")

    def test_new_version_prepended_at_top(self):
        local = b"# [1.0.0]\n- Old feature\n"
        remote = (
            b"# [1.1.0]\n"
            b"- New feature A\n"
            b"- Bug fix B\n\n"
            b"# [1.0.0]\n"
            b"- Old feature\n"
        )
        diff = self.main_mod._compute_changelog_diff(local, remote)
        expected = "# [1.1.0]\n- New feature A\n- Bug fix B"
        self.assertEqual(diff, expected)

    def test_new_version_appended_at_bottom(self):
        local = b"# [1.0.0]\n- Old feature\n"
        remote = (
            b"# [1.0.0]\n"
            b"- Old feature\n\n"
            b"# [1.1.0]\n"
            b"- Appended feature\n"
        )
        diff = self.main_mod._compute_changelog_diff(local, remote)
        expected = "# [1.1.0]\n- Appended feature"
        self.assertEqual(diff, expected)

    def test_arbitrary_line_diff_fallback(self):
        local = b"- Line 1\n- Line 2\n"
        remote = b"- Line 1\n- Line 1.5 modified\n- Line 2\n"
        diff = self.main_mod._compute_changelog_diff(local, remote)
        self.assertIn("Line 1.5 modified", diff)

    def test_remote_html_parsing(self):
        remote_files = {
            "notification.html": b'<span class="warning-icon">!</span><span>HTML announcement</span>',
            "update_banner.html": b'<span>Custom update banner</span>',
        }
        res_notif = self.main_mod._parse_remote_html(remote_files, "notification.html")
        res_update = self.main_mod._parse_remote_html(remote_files, "update_banner.html")
        self.assertIn("HTML announcement", res_notif)
        self.assertIn("Custom update banner", res_update)


if __name__ == "__main__":
    unittest.main()
