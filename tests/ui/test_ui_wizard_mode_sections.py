#!/usr/bin/env python3
"""
UI E2E Test: Wizard Mode Selection & Step 2 Section Visibility
Verifies:
1. Selecting Cascade + Sub displays Cascade Dual Node and Sub-Server sections.
2. Selecting Freedom Only displays Single Node section and hides extra sections.
3. Selecting Recovery mode displays Recovery section.
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
    log("🚀 UI TEST: WIZARD MODE SELECTION & SECTION VISIBILITY", "info")
    log("==================================================", "info")

    server, server_url, _, _, sandbox_dir = start_sandboxed_control_panel("mode_sections")

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(viewport={"width": 1400, "height": 900})
        page = await context.new_page()

        try:
            await page.goto(server_url, wait_until="networkidle")

            # 1. Cascade + Sub (3 nodes)
            log("Checking 'Cascade + Sub' mode...", "info")
            await page.click("input[name='deploy_mode'][value='cascade_sub']")
            await page.click("#btnNextStep1")
            await page.wait_for_timeout(300)

            assert await page.is_visible("#cascadeNodeSection"), "Cascade Dual Node section should be visible"
            assert await page.is_visible("#subServerSshSection"), "Sub-Server SSH section should be visible"
            log("✅ [Cascade+Sub] Cascade and Sub-server sections are visible on Step 2.", "success")

            # 2. Freedom Single Node
            log("Checking 'Freedom Only' single mode...", "info")
            await page.click("#btnBackToStep1")
            await page.wait_for_timeout(300)
            await page.click("input[name='deploy_mode'][value='freedom_only']")
            await page.click("#btnNextStep1")
            await page.wait_for_timeout(300)

            assert await page.is_visible("#singleNodeSection"), "Single SSH section should be visible"
            assert not await page.is_visible("#subServerSshSection"), "Sub-Server section must be hidden"
            assert not await page.is_visible("#cascadeNodeSection"), "Cascade section must be hidden"
            log("✅ [Freedom Only] Single node section is visible, extra sections hidden.", "success")

            # 3. Recovery Mode
            log("Checking 'Recovery' mode...", "info")
            await page.click("#btnBackToStep1")
            await page.wait_for_timeout(300)
            await page.click("input[name='deploy_mode'][value='recovery']")
            await page.click("#btnNextStep1")
            await page.wait_for_timeout(300)

            assert await page.is_visible("#recoveryNodeSection"), "Recovery SSH section should be visible"
            log("✅ [Recovery] Recovery section is visible.", "success")

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
