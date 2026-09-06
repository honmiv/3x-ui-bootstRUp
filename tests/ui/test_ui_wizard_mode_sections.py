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
from tests.ui.ui_helpers import start_sandboxed_control_panel, mock_ssh_success


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
            await page.wait_for_timeout(500)

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

            # 3. Freedom Node + Sub Server (freedom_sub)
            log("Checking 'Freedom + Sub Server' mode...", "info")
            await page.click("#btnBackToStep1")
            await page.wait_for_timeout(300)
            await page.click("input[name='deploy_mode'][value='freedom_sub']")
            await page.click("#btnNextStep1")
            await page.wait_for_timeout(300)

            assert await page.is_visible("#singleNodeSection"), "Single SSH section should be visible for Freedom Node"
            assert await page.is_visible("#subServerSshSection"), "Sub-Server SSH section should be visible"
            assert not await page.is_visible("#cascadeNodeSection"), "Cascade Dual Node section must be hidden"
            log("✅ [Freedom+Sub] Step 2 sections verified.", "success")

            # Check Step 3 for freedom_sub
            # Temporarily fill dummy values to proceed to Step 3 or click Step 3 button
            await page.click("#btnBackToStep1")
            await page.wait_for_timeout(300)

            # 3b. Sub Server Only mode (sub_only) - Step 2 and Step 3 SSH port change
            log("Checking 'Sub Server Only' mode and Step 3 SSH port option...", "info")
            await page.click("input[name='deploy_mode'][value='sub_only']")
            await page.click("#btnNextStep1")
            await page.wait_for_timeout(300)

            assert await page.is_visible("#subServerSshSection"), "Sub-Server SSH section should be visible"
            assert not await page.is_visible("#singleNodeSection"), "Single section must be hidden"
            assert not await page.is_visible("#cascadeNodeSection"), "Cascade section must be hidden"

            await page.fill("#sub_vps_host", "sub.example.com")
            await page.fill("#sub_vps_password", "pass123")
            await mock_ssh_success(page)
            await page.click("#btnTestSSH")
            await page.wait_for_selector("#btnNext1:not(.hidden)", state="attached", timeout=5000)
            await page.click("#btnNext1")
            await page.wait_for_timeout(300)

            assert await page.is_visible("#subServerPanelSection"), "Sub Server panel section should be visible on Step 3"
            assert await page.is_visible("#generalSettingsCard"), "General settings card should be visible on Step 3 for sub_only"
            assert not await page.is_visible("#xuiVersionBlock"), "XUI version block should be hidden in sub_only"
            assert not await page.is_visible("#happRoutingBlock"), "Happ routing block should be hidden in sub_only"

            title_text = await page.text_content("#generalSettingsTitle")
            assert "безопасности" in title_text.lower(), f"Unexpected title: {title_text}"
            badge_text = await page.text_content("#generalSettingsBadge")
            assert "security" in badge_text.lower(), f"Unexpected badge: {badge_text}"

            sub_ssh_cb = page.locator("#opt_change_ssh_port")
            assert await sub_ssh_cb.count() == 1, "SSH port change checkbox should exist on Step 3"
            await page.click("label[for='opt_change_ssh_port']")
            assert await sub_ssh_cb.is_checked(), "Checkbox should be checked"
            sub_ssh_row = page.locator("#sshPortConfigRow")
            await sub_ssh_row.wait_for(state="visible", timeout=3000)
            custom_val = await page.input_value("#custom_ssh_port")
            assert custom_val == "22222", f"Expected default 22222, got {custom_val}"
            log("✅ [Sub Only] SSH port change option verified on Step 3.", "success")

            await page.click("#btnBackToStep2")
            await page.wait_for_timeout(300)
            await page.click("#btnBackToStep1")
            await page.wait_for_timeout(300)

            # 4. Recovery Mode
            log("Checking 'Recovery' mode...", "info")
            await page.click("input[name='deploy_mode'][value='recovery']")
            await page.click("#btnNextStep1")
            await page.wait_for_timeout(300)

            assert await page.is_visible("#recoveryNodeSection"), "Recovery SSH section should be visible"
            log("✅ [Recovery] Recovery section is visible.", "success")

            # 5. Update 3X-UI Mode (Step 2 and Step 3 SSH port change)
            log("Checking 'Update 3X-UI' mode and Step 3 SSH port option...", "info")
            await page.click("#btnBackToStep1")
            await page.wait_for_timeout(300)
            await page.click("input[name='deploy_mode'][value='update_3xui']")
            await page.click("#btnNextStep1")
            await page.wait_for_timeout(300)

            assert await page.is_visible("#updateNodeSection"), "Update node section should be visible on Step 2"
            await page.fill("#update_vps_host", "xui.example.com")
            await page.fill("#update_vps_password", "pass123")
            await mock_ssh_success(page)
            await page.click("#btnTestSSH")
            await page.wait_for_selector("#btnNext1:not(.hidden)", state="attached", timeout=5000)
            await page.click("#btnNext1")
            await page.wait_for_timeout(300)

            assert await page.is_visible("#updatePanelSection"), "Update panel section should be visible on Step 3"
            update_ssh_cb = page.locator("#opt_update_change_ssh_port")
            assert await update_ssh_cb.count() == 1, "SSH port change checkbox should exist in Update 3X-UI section"
            await page.click("label[for='opt_update_change_ssh_port']")
            assert await update_ssh_cb.is_checked(), "Checkbox should be checked"
            update_ssh_row = page.locator("#sshPortConfigRowUpdate")
            await update_ssh_row.wait_for(state="visible", timeout=3000)
            custom_val = await page.input_value("#custom_update_ssh_port")
            assert custom_val == "22222", f"Expected default 22222, got {custom_val}"
            log("✅ [Update 3X-UI] SSH port change option verified on Step 3.", "success")

            # 6. Update Sub Mode (Step 2 and Step 3 SSH port change)
            log("Checking 'Update Sub' mode and Step 3 SSH port option...", "info")
            await page.click("#btnBackToStep2")
            await page.wait_for_timeout(300)
            await page.click("#btnBackToStep1")
            await page.wait_for_timeout(300)
            await page.click("input[name='deploy_mode'][value='update_sub']")
            await page.click("#btnNextStep1")
            await page.wait_for_timeout(300)

            assert await page.is_visible("#subServerSshSection"), "Sub server SSH section should be visible on Step 2"
            await page.fill("#sub_vps_host", "sub.example.com")
            await page.fill("#sub_vps_password", "pass123")
            await mock_ssh_success(page)
            await page.click("#btnTestSSH")
            await page.wait_for_selector("#btnNext1:not(.hidden)", state="attached", timeout=5000)
            await page.click("#btnNext1")
            await page.wait_for_timeout(300)

            assert await page.is_visible("#updateSubSection"), "Update sub section should be visible on Step 3"
            update_sub_ssh_cb = page.locator("#opt_update_sub_change_ssh_port")
            assert await update_sub_ssh_cb.count() == 1, "SSH port change checkbox should exist in Update Sub section"
            await page.click("label[for='opt_update_sub_change_ssh_port']")
            assert await update_sub_ssh_cb.is_checked(), "Checkbox should be checked"
            update_sub_ssh_row = page.locator("#sshPortConfigRowUpdateSub")
            await update_sub_ssh_row.wait_for(state="visible", timeout=3000)
            custom_sub_val = await page.input_value("#custom_update_sub_ssh_port")
            assert custom_sub_val == "22222", f"Expected default 22222, got {custom_sub_val}"
            log("✅ [Update Sub] SSH port change option verified on Step 3.", "success")

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
