#!/usr/bin/env python3
"""
UI E2E Test: Client-side Form Validation
Verifies:
1. Missing required domain/host prevents advancing to Step 3.
2. Clicking #btnTestSSH with empty inputs shows validation error in #testResult.
3. #btnNext1 remains hidden until valid parameters are provided.
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
    log("🚀 UI TEST: CLIENT-SIDE FORM VALIDATION", "info")
    log("==================================================", "info")

    server, server_url, _, _, sandbox_dir = start_sandboxed_control_panel("validation")

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(viewport={"width": 1400, "height": 900})
        page = await context.new_page()

        try:
            await page.goto(server_url, wait_until="networkidle")

            # 1. Step 1 -> Choose Cascade
            await page.click("input[name='deploy_mode'][value='cascade']")
            await page.click("#btnNextStep1")
            await page.wait_for_timeout(300)

            # 2. Leave hosts empty and click Test SSH
            log("Clicking #btnTestSSH with empty host fields...", "info")
            await page.click("#btnTestSSH")
            await page.wait_for_timeout(300)

            # 3. Assert #btnNext1 is still hidden and error message is displayed
            btn_next1_classes = await page.locator("#btnNext1").get_attribute("class")
            assert "hidden" in btn_next1_classes, "btnNext1 must remain hidden when required fields are missing!"

            test_result_text = await page.locator("#testResult").text_content()
            assert "❌" in test_result_text or "Укажите" in test_result_text
            log(f"Validation error correctly displayed: '{test_result_text.strip()}'", "success")

            # 4. Assert Step 3 is NOT visible
            assert not await page.is_visible("#step3"), "Step 3 should not be accessible when validation fails!"
            log("✅ [Validation Verified] Incomplete configuration properly blocked.", "success")

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
