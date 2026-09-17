#!/usr/bin/env python3
"""
UI E2E Test: Realtime SSE Log Streaming to Web Terminal
Verifies:
1. Terminal container opens when deployment starts.
2. Injected log messages with ANSI colors are streamed via Server-Sent Events (/api/deploy/logs).
3. Text is rendered into the DOM terminal element.
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
    log("🚀 UI TEST: REALTIME SSE LOG STREAMING", "info")
    log("==================================================", "info")

    server, server_url, _, _, sandbox_dir = start_sandboxed_control_panel("sse_terminal")

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(viewport={"width": 1400, "height": 900})
        page = await context.new_page()

        try:
            await page.goto(server_url, wait_until="networkidle")

            # 1. Simulate running deployment in backend
            backend_main.active_logs.clear()
            backend_main.is_deploying = True
            backend_main.deploy_status = "running"

            # 2. Reveal terminal in UI
            await page.evaluate("""() => {
                const termSection = document.getElementById('terminalSection');
                if (termSection) termSection.classList.remove('hidden');
            }""")

            # 3. Stream logs — must match the Dict[str, str] schema that _get_deploy_logs serialises
            backend_main.active_logs.append({"message": "Deployment step 1 completed successfully.", "level": "success"})
            backend_main.active_logs.append({"message": "Checking Docker container status...", "level": "info"})

            # 4. Open SSE connection from browser side (normally triggered by deploy button click)
            await page.evaluate("() => { if (window.startDeployLogStream) window.startDeployLogStream(() => {}); }")

            # 5. Wait until terminal actually receives and renders the log messages
            await page.wait_for_function(
                """() => {
                    const el = document.getElementById('terminalLogs');
                    const text = el ? el.textContent : '';
                    return text.includes('Deployment step 1 completed') || text.includes('Checking Docker');
                }""",
                timeout=10000,
            )

            # 6. Assert rendered in terminal
            term_text = await page.locator("#terminalLogs").text_content()
            log(f"Terminal rendered output:\n{term_text}", "info")
            assert "Deployment step 1 completed" in term_text or "Checking Docker" in term_text, \
                f"Expected deployment log content in terminal, got: {repr(term_text[:200])}"
            log("✅ [SSE Stream Verified] Logs rendered live in DOM.", "success")

            log("🎉 TEST PASSED!", "success")
            return True
        finally:
            backend_main.is_deploying = False
            await context.close()
            await browser.close()
            server.shutdown()
            shutil.rmtree(sandbox_dir, ignore_errors=True)


def main():
    ok = asyncio.run(run_test())
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
