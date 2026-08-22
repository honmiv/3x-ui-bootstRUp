#!/usr/bin/env python3
"""
UI E2E Test: 3x-ui Versions Dropdown Population (/api/xui_versions)
Verifies:
1. Navigating to Step 3 of deployment form.
2. The #xui_version and #update_xui_version dropdowns are populated with versions from API.
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
from tests.ui.ui_helpers import mock_ssh_success, start_sandboxed_control_panel


async def run_test() -> bool:
    log("==================================================", "info")
    log("🚀 UI TEST: XUI VERSIONS DROPDOWN API INTEGRATION", "info")
    log("==================================================", "info")

    server, server_url, _, _, sandbox_dir = start_sandboxed_control_panel("xui_versions")

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(viewport={"width": 1400, "height": 900})
        page = await context.new_page()

        try:
            await page.goto(server_url, wait_until="networkidle")

            # 1. Advance to Step 3
            await page.click("input[name='deploy_mode'][value='freedom_only']")
            await page.click("#btnNextStep1")
            await page.wait_for_timeout(300)
            await page.fill("#vps_host", "freedom.test.local")

            await mock_ssh_success(page)
            await page.click("#btnTestSSH")
            await page.wait_for_selector("#btnNext1:not(.hidden)", state="attached", timeout=5000)
            await page.click("#btnNext1")
            await page.wait_for_timeout(300)

            # 2. Check versions populated
            version_options = await page.eval_on_selector_all(
                "#xui_version option, #update_xui_version option",
                "options => options.map(o => o.value)"
            )
            log(f"Loaded XUI versions in select: {version_options[:5]}...", "info")
            assert len(version_options) > 0, "XUI versions dropdown should have options populated!"
            assert "latest" in version_options or any("." in v for v in version_options)
            log("✅ [XUI Versions Verified] Dropdown populated with Docker tags.", "success")

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
