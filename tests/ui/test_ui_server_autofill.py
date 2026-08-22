#!/usr/bin/env python3
"""
UI E2E Test: Server Decryption & Autofill («Заполнить поля»)
Verifies:
1. Creating a server card with secret credentials.
2. Navigating to Step 2 (Server Connection Form).
3. Clicking «Заполнить поля» on the card.
4. Target selection and assertion that decrypted credentials populate active inputs.
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
from tests.ui.ui_helpers import start_sandboxed_control_panel


async def run_test() -> bool:
    log("==================================================", "info")
    log("🚀 UI TEST: SERVER DECRYPTION & AUTOFILL", "info")
    log("==================================================", "info")

    server, server_url, _, _, sandbox_dir = start_sandboxed_control_panel("autofill")

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(viewport={"width": 1400, "height": 900})
        page = await context.new_page()

        try:
            await page.goto(server_url, wait_until="networkidle")

            # 1. Add server
            await page.fill("#sm_host", "95.217.100.50")
            await page.fill("#sm_user", "root")
            await page.fill("#sm_port", "2222")
            await page.fill("#sm_pass", "AutofillPass2026!")
            await page.click("#btnSaveServer")
            await page.wait_for_selector("#masterPasswordModal.active", state="attached", timeout=5000)
            await page.fill("#masterPasswordInput", "1234")
            await page.click("#btnSubmitMasterPassword")
            await page.wait_for_selector("#masterPasswordModal.active", state="detached", timeout=5000)

            # 2. Navigate to Step 2
            log("Navigating to Step 2...", "info")
            await page.click("#btnNextStep1")
            await page.wait_for_timeout(300)

            # 3. Click Autofill button on server card
            card = page.locator(".server-card").first
            await card.wait_for(state="visible", timeout=5000)
            fill_btn = card.locator("button[title='Заполнить поля']")
            await fill_btn.click()
            await page.wait_for_timeout(300)

            # If target host modal opens, choose target
            fill_modal = page.locator("#fillServerModal.active")
            if await fill_modal.count() > 0:
                await page.click("#fillServerButtons button")
                await page.wait_for_selector("#fillServerModal.active", state="detached", timeout=3000)

            await page.wait_for_timeout(500)

            # 4. Verify populated values
            host_val = await page.input_value("#freedom_host") or await page.input_value("#proxy_host") or await page.input_value("#vps_host")
            pass_val = await page.input_value("#freedom_password") or await page.input_value("#proxy_password") or await page.input_value("#vps_password")

            assert host_val == "95.217.100.50", f"Expected '95.217.100.50', got '{host_val}'"
            assert pass_val == "AutofillPass2026!", f"Expected 'AutofillPass2026!', got '{pass_val}'"
            log("✅ [Autofill Verified] Host and decrypted password successfully inserted into form.", "success")

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
