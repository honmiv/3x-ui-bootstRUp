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

            # 2. Check versions populated — wait for async loadXuiVersions() to complete
            # The frontend fetches /api/xui_versions on load (async); we must wait
            # for the select to be repopulated beyond the initial "Загрузка версий..." option.
            try:
                await page.wait_for_function(
                    """() => {
                        const sel = document.getElementById('xui_version');
                        if (!sel) return false;
                        // Still showing placeholder — not yet loaded
                        if (sel.options.length <= 1 && sel.options[0]?.value === '') return false;
                        // Loaded — at least 1 option with non-empty value
                        return sel.options.length >= 1 && sel.options[0]?.value !== '';
                    }""",
                    timeout=12000,
                )
            except Exception:
                log("⚠ Version dropdown did not populate in time (network issue?)", "info")

            version_options = await page.eval_on_selector_all(
                "#xui_version option, #update_xui_version option",
                "options => options.map(o => o.value)"
            )
            log(f"Loaded XUI versions in select: {version_options[:5]}...", "info")
            assert len(version_options) > 0, "XUI versions dropdown should have options populated!"
            assert version_options[0] == "latest", f"Expected 'latest' at top of dropdown, got '{version_options[0]}'"

            # 3. Check default selection — prefer a concrete release, but gracefully
            #    accept 'latest' when ghcr.io was unreachable (fallback returns only latest).
            selected_val = await page.locator("#xui_version").input_value()
            has_concrete = any(v != "latest" for v in version_options)
            if has_concrete:
                assert selected_val != "latest", f"Selected version should be concrete release, got '{selected_val}'"
                log(f"✅ [XUI Default Verified] Selected default is '{selected_val}' (not 'latest').", "success")
            else:
                log(f"⚠ [XUI Default Skipped] Only 'latest' available (ghcr.io unreachable?). Selected='{selected_val}'.", "info")

            # 4. Verify user can explicitly select 'latest'
            assert "latest" in version_options, "'latest' option should be present in dropdown list"
            await page.select_option("#xui_version", "latest", force=True)
            selected_latest = await page.locator("#xui_version").input_value()
            assert selected_latest == "latest", f"Expected 'latest' to be selectable, got '{selected_latest}'"
            log("✅ [XUI 'latest' Option Verified] User can explicitly select 'latest'.", "success")

            log("✅ [XUI Versions Verified] Dropdown populated with Docker tags.", "success")

            log("🎉 TEST PASSED!", "success")
            return True
        except Exception as e:
            import traceback
            traceback.print_exc()
            log(f"Test error: {e}", "error")
            return False
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
