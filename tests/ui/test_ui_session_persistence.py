#!/usr/bin/env python3
"""
UI E2E Test: Session State Auto-Save & F5 Restoration
Verifies:
1. Entering deployment parameters.
2. setup_backup.yml is auto-saved.
3. Passwords and SSH keys are STRIPPED from disk (security assertion).
4. Reloading the page (F5) restores entered domains and settings without restoring passwords.
"""

import asyncio
import os
import shutil
import sys

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

import yaml
from playwright.async_api import async_playwright
from tests.helpers import log
from tests.ui.ui_helpers import mock_ssh_success, start_sandboxed_control_panel


async def run_test() -> bool:
    log("==================================================", "info")
    log("🚀 UI TEST: SESSION STATE PERSISTENCE & F5 RESTORATION", "info")
    log("==================================================", "info")

    server, server_url, _, backup_file, sandbox_dir = start_sandboxed_control_panel("session_state")

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(viewport={"width": 1400, "height": 900})
        page = await context.new_page()

        try:
            await page.goto(server_url, wait_until="networkidle")

            # 1. Fill parameters
            await page.click("input[name='deploy_mode'][value='cascade']")
            await page.click("#btnNextStep1")
            await page.wait_for_timeout(300)

            await page.fill("#freedom_host", "freedom.example.org")
            await page.fill("#freedom_password", "FreedomSecretPass123!")
            await page.fill("#proxy_host", "proxy.example.org")
            await page.fill("#proxy_password", "ProxySecretPass123!")

            # 2. Advance to Step 3 to trigger auto-save
            await mock_ssh_success(page)
            await page.click("#btnTestSSH")
            await page.wait_for_selector("#btnNext1:not(.hidden)", state="attached", timeout=5000)
            await page.click("#btnNext1")
            await page.wait_for_timeout(500)

            # 3. Security Assertion on setup_backup.yml
            assert os.path.exists(backup_file), "setup_backup.yml should exist"
            with open(backup_file, "r", encoding="utf-8") as f:
                content = f.read()

            assert "FreedomSecretPass123!" not in content, "SECURITY ALERT: Plaintext password found in setup_backup.yml!"
            assert "ProxySecretPass123!" not in content, "SECURITY ALERT: Plaintext password found in setup_backup.yml!"
            assert "freedom.example.org" in content
            assert "proxy.example.org" in content
            log("✅ [SECURITY VERIFIED] setup_backup.yml auto-saved without passwords.", "success")

            # 4. Reload (F5) and verify form restoration
            log("Reloading page (F5)...", "info")
            await page.reload(wait_until="networkidle")
            await page.click("#btnNextStep1")
            await page.wait_for_timeout(300)

            restored_f = await page.input_value("#freedom_host")
            restored_p = await page.input_value("#proxy_host")
            restored_pass = await page.input_value("#freedom_password")

            assert restored_f == "freedom.example.org"
            assert restored_p == "proxy.example.org"
            assert restored_pass == "", "Password must be empty on page reload"
            log("✅ [Restoration Verified] Domains restored, password inputs kept blank.", "success")

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
