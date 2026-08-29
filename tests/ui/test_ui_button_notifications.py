#!/usr/bin/env python3
"""
UI E2E Test: Button Notifications & Custom Modals
Verifies:
1. Clicking «Обновить скрипт» (#btnUpdateSources) opens #customConfirmModal with update title.
2. Clicking «Перезапустить» (#btnRestart) opens #customConfirmModal with restart title.
3. Clicking «Выключить» (#btnShutdown) opens #customConfirmModal with shutdown title & danger styling.
4. Custom toast container (#toastContainer) displays toasts without using browser native dialogs.
5. No native browser dialogs (alert/confirm) are triggered.
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
    log("🚀 UI TEST: BUTTON NOTIFICATIONS & CUSTOM MODALS", "info")
    log("==================================================", "info")

    server, server_url, _, _, sandbox_dir = start_sandboxed_control_panel("button_notifications")
    native_dialog_fired = False

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(viewport={"width": 1400, "height": 900})
        page = await context.new_page()

        def handle_dialog(dialog):
            nonlocal native_dialog_fired
            native_dialog_fired = True
            log(f"❌ [UNEXPECTED NATIVE DIALOG] Type: {dialog.type}, Message: {dialog.message}", "error")
            asyncio.create_task(dialog.dismiss())

        page.on("dialog", handle_dialog)

        try:
            await page.goto(server_url, wait_until="networkidle")

            # 1. Test #btnUpdateSources modal
            log("Testing '#btnUpdateSources' modal...", "info")
            btn_update = page.locator("#btnUpdateSources")
            if await btn_update.count() > 0:
                await btn_update.click()
                await page.wait_for_selector("#customConfirmModal.active", state="attached", timeout=3000)
                title = await page.locator("#customModalTitle").text_content()
                assert "Обновление деплоера" in title, f"Expected 'Обновление деплоера', got '{title}'"
                log("Confirm modal displayed for '#btnUpdateSources'. Cancelling...", "info")
                await page.click("#customModalCancelBtn")
                await page.wait_for_selector("#customConfirmModal.active", state="detached", timeout=3000)
                log("✅ [UpdateSources Modal Verified]", "success")

            # 2. Test #btnRestart modal
            log("Testing '#btnRestart' modal...", "info")
            btn_restart = page.locator("#btnRestart")
            if await btn_restart.count() > 0:
                await btn_restart.click()
                await page.wait_for_selector("#customConfirmModal.active", state="attached", timeout=3000)
                title = await page.locator("#customModalTitle").text_content()
                assert "Перезапуск сервера" in title, f"Expected 'Перезапуск сервера', got '{title}'"
                log("Confirm modal displayed for '#btnRestart'. Cancelling...", "info")
                await page.click("#customModalCancelBtn")
                await page.wait_for_selector("#customConfirmModal.active", state="detached", timeout=3000)
                log("✅ [Restart Modal Verified]", "success")

            # 3. Test #btnShutdown modal
            log("Testing '#btnShutdown' modal...", "info")
            btn_shutdown = page.locator("#btnShutdown")
            if await btn_shutdown.count() > 0:
                await btn_shutdown.click()
                await page.wait_for_selector("#customConfirmModal.active", state="attached", timeout=3000)
                title = await page.locator("#customModalTitle").text_content()
                assert "Выключение сервера" in title, f"Expected 'Выключение сервера', got '{title}'"
                confirm_btn_class = await page.locator("#customModalConfirmBtn").get_attribute("class")
                assert "btn-danger-action" in confirm_btn_class, f"Expected danger button class, got '{confirm_btn_class}'"
                log("Confirm modal displayed for '#btnShutdown' with danger styling. Cancelling...", "info")
                await page.click("#customModalCancelBtn")
                await page.wait_for_selector("#customConfirmModal.active", state="detached", timeout=3000)
                log("✅ [Shutdown Modal Verified]", "success")

            # 4. Test custom toast system
            log("Testing custom showToast() invocation...", "info")
            await page.evaluate("showToast('Тестовое уведомление UI', 'success')")
            await page.wait_for_selector("#toastContainer .toast-success", state="attached", timeout=3000)
            toast_text = await page.locator("#toastContainer .toast-message").text_content()
            assert "Тестовое уведомление UI" in toast_text, f"Expected toast message, got '{toast_text}'"
            log("✅ [Custom Toast Verified]", "success")

            # 5. Assert no native browser dialogs were ever triggered
            assert not native_dialog_fired, "A native browser dialog was fired instead of custom UI modal/toast!"
            log("✅ [No Native Dialogs Verified] Zero native dialogs triggered.", "success")

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
