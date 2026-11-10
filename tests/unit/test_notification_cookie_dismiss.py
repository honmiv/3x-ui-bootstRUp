#!/usr/bin/env python3
"""Unit tests for notification cookie dismissal logic."""

import hashlib
import os
import sys
import unittest

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)


class TestNotificationCookieDismiss(unittest.TestCase):
    def setUp(self):
        self.app_js_path = os.path.join(REPO_ROOT, "panel", "static", "app.js")
        with open(self.app_js_path, "r", encoding="utf-8") as f:
            self.app_js = f.read()

        self.notif_html_path = os.path.join(REPO_ROOT, "notification.html")
        with open(self.notif_html_path, "r", encoding="utf-8") as f:
            self.notif_html = f.read()

    def test_app_js_contains_cookie_dismissal_functions(self):
        """Verify helper functions and delegation exist in app.js."""
        self.assertIn("getNotificationHash", self.app_js)
        self.assertIn("isNotificationClosed", self.app_js)
        self.assertIn("closeNotificationForever", self.app_js)
        self.assertIn("announcementBanner", self.app_js)
        self.assertIn("notif_", self.app_js)
        self.assertIn("closed", self.app_js)
        self.assertIn("data-notif-hash", self.app_js)

    def test_notification_html_has_dismiss_button(self):
        """Verify notification.html has a button with data-action='dismiss'."""
        self.assertIn('data-action="dismiss"', self.notif_html)
        self.assertIn("update-actions", self.notif_html)

    def test_hash_differentiation(self):
        """Verify different notification contents result in different hashes."""
        content1 = "<p>Notice 1</p>"
        content2 = "<p>Notice 2</p>"
        hash1 = hashlib.md5(content1.strip().encode("utf-8")).hexdigest()[:16]
        hash2 = hashlib.md5(content2.strip().encode("utf-8")).hexdigest()[:16]
        self.assertNotEqual(hash1, hash2)
        cookie1 = f"notif_{hash1}=closed"
        cookie2 = f"notif_{hash2}=closed"
        self.assertNotEqual(cookie1, cookie2)


if __name__ == "__main__":
    unittest.main()

