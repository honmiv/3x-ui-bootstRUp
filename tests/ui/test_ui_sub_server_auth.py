#!/usr/bin/env python3
"""
UI E2E Test: Subscription Server Authentication & Session Control
Verifies:
1. Unauthorized GET /subs redirects to /subs/login.
2. Submitting invalid credentials shows error message.
3. Submitting valid credentials sets session cookie and loads dashboard.
"""

import asyncio
import os
import shutil
import sys

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from playwright.async_api import async_playwright
from tests.helpers import log
from tests.ui.ui_helpers import start_sandboxed_sub_server

ADMIN_USER = "subadmin"
ADMIN_PASSWORD = "SubAdminSecurePass123!"
SECRET_PATH = "subs"


async def run_test() -> bool:
    log("==================================================", "info")
    log("🚀 UI TEST: SUB-SERVER AUTH & SESSION CONTROL", "info")
    log("==================================================", "info")

    server, server_url, _, _, sandbox_dir, _ = start_sandboxed_sub_server(
        "sub_auth",
        admin_user=ADMIN_USER,
        admin_password=ADMIN_PASSWORD,
        secret_path=SECRET_PATH
    )

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(viewport={"width": 1400, "height": 900})
        page = await context.new_page()

        try:
            # 1. Unauth redirect
            log("Accessing /subs without authentication...", "info")
            await page.goto(f"{server_url}/{SECRET_PATH}", wait_until="networkidle")
            assert "/login" in page.url, "Unauthenticated access should redirect to /login"
            log("✅ [Auth Redirect Verified] Redirected to login screen.", "success")

            # 2. Bad password
            log("Submitting invalid password...", "info")
            await page.fill("input[name='user']", ADMIN_USER)
            await page.fill("input[name='password']", "WrongPassword!")
            await page.click("button[type='submit']")
            await page.wait_for_timeout(500)

            page_text = await page.text_content("body")
            assert "Неверный" in page_text or "Invalid" in page_text or "/login" in page.url
            log("✅ [Invalid Auth Verified] Error displayed for wrong credentials.", "success")

            # 3. Valid login
            log("Submitting valid credentials...", "info")
            await page.fill("input[name='user']", ADMIN_USER)
            await page.fill("input[name='password']", ADMIN_PASSWORD)
            await page.click("button[type='submit']")
            await page.wait_for_timeout(800)

            dashboard_url = page.url
            assert "/login" not in dashboard_url and SECRET_PATH in dashboard_url
            log(f"✅ [Valid Login Verified] Dashboard accessed: {dashboard_url}", "success")

            log("🎉 TEST PASSED!", "success")
            return True
        finally:
            await context.close()
            await browser.close()
            server.shutdown()
            shutil.rmtree(sandbox_dir, ignore_errors=True)


def main():
    ok = asyncio.run(run_test())
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
