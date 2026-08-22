#!/usr/bin/env python3
"""
UI E2E Test: Deploy Stop & Cancellation Confirmation
Verifies:
1. Clicking «Остановить деплой» (#btnStopDeploy) while deploying.
2. Custom confirmation modal #customConfirmModal opens.
3. Confirming sends POST /api/deploy/stop and sets cancel_requested flag on backend.
"""

import asyncio
import os
import shutil
import sys

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

import main as backend_main
from playwright.async_api import async_playwright
from tests.helpers import log
from tests.ui.ui_helpers import start_sandboxed_control_panel


async def run_test() -> bool:
    log("==================================================", "info")
    log("🚀 UI TEST: DEPLOY STOP & CANCELLATION", "info")
    log("==================================================", "info")

    server, server_url, _, _, sandbox_dir = start_sandboxed_control_panel("deploy_stop")

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(viewport={"width": 1400, "height": 900})
        page = await context.new_page()

        try:
            await page.goto(server_url, wait_until="networkidle")

            # 1. Simulate active deploy
            backend_main.is_deploying = True
            backend_main.cancel_requested = False

            await page.evaluate("""() => {
                document.querySelectorAll('.step-content').forEach(s => {
                    s.classList.add('hidden');
                    s.style.display = 'none';
                });
                const step4 = document.getElementById('step4');
                if (step4) {
                    step4.classList.remove('hidden');
                    step4.style.display = 'block';
                }
                const term = document.getElementById('terminalSection');
                if (term) {
                    term.classList.remove('hidden');
                    term.style.display = 'block';
                }
                const btnStop = document.getElementById('btnStopDeploy');
                if (btnStop) {
                    btnStop.classList.remove('hidden');
                    btnStop.style.display = 'inline-flex';
                }
            }""")

            # 2. Click Stop Deploy
            log("Clicking '#btnStopDeploy'...", "info")
            await page.click("#btnStopDeploy")
            await page.wait_for_selector("#customConfirmModal.active", state="attached", timeout=3000)

            # 3. Confirm in modal
            log("Confirming cancellation modal...", "info")
            await page.click("#customModalConfirmBtn")
            await page.wait_for_selector("#customConfirmModal.active", state="detached", timeout=3000)
            await page.wait_for_timeout(500)

            # 4. Backend flag check
            assert backend_main.cancel_requested is True or backend_main.is_deploying is False, "Backend cancel_requested was not set!"
            log("✅ [Cancellation Verified] Stop signal dispatched and received.", "success")

            log("🎉 TEST PASSED!", "success")
            return True
        finally:
            backend_main.is_deploying = False
            backend_main.cancel_requested = False
            await context.close()
            await browser.close()
            server.shutdown()
            shutil.rmtree(sandbox_dir, ignore_errors=True)


def main():
    ok = asyncio.run(run_test())
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
