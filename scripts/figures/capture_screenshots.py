"""Capture paper-quality screenshots of the running review app + dashboard.

Assumes:
  - review app on http://localhost:5556 with HTTP Basic auth admin:masseto
  - dashboard on http://localhost:5555 with HTTP Basic auth admin:masseto

Outputs to paper/figures/screenshots/.
"""
from __future__ import annotations

import asyncio
import base64
from pathlib import Path

from playwright.async_api import async_playwright

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "paper" / "figures" / "screenshots"
OUT.mkdir(parents=True, exist_ok=True)

REVIEW_BASE = "http://localhost:5556"
DASH_BASE = "http://localhost:5555"
USER, PASSWORD = "admin", "masseto"

VIEWPORT = {"width": 1280, "height": 800}


async def shoot(page, url, out_name, full_page=True):
    print(f"  visiting {url}")
    await page.goto(url, wait_until="networkidle")
    await page.wait_for_timeout(800)
    path = OUT / f"{out_name}.png"
    await page.screenshot(path=str(path), full_page=full_page)
    print(f"  wrote {path.relative_to(ROOT)}")


async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)

        # context with HTTP Basic auth
        ctx = await browser.new_context(
            viewport=VIEWPORT,
            http_credentials={"username": USER, "password": PASSWORD},
            device_scale_factor=2,
        )
        page = await ctx.new_page()

        # Review app — login (this is the inner login form, basic auth pre-passed)
        await shoot(page, f"{REVIEW_BASE}/login", "review_login")

        # Try logging in via the form so we can capture authenticated pages.
        # Fall back to direct visits if the form submission fails.
        try:
            # Try common reviewer creds; the app supports register so we try that path too
            # Existing reviewer or register a fresh one to capture the dashboard
            await page.goto(f"{REVIEW_BASE}/register", wait_until="networkidle")
            # If form fields are present, register a paper-screenshot user
            email = await page.query_selector('input[name="email"]')
            if email:
                await page.fill('input[name="email"]', "paper-reviewer@oenobench.org")
                pw = await page.query_selector('input[name="password"]')
                if pw:
                    await page.fill('input[name="password"]', "paper-reviewer")
                # WSET level (try selecting Diploma)
                wset = await page.query_selector('select[name="wset_level"]')
                if wset:
                    await wset.select_option(label="WSET Diploma")
                # name
                name_field = await page.query_selector('input[name="name"]')
                if name_field:
                    await page.fill('input[name="name"]', "OenoBench Reviewer")
                btn = await page.query_selector('button[type="submit"]')
                if btn:
                    await btn.click()
                    await page.wait_for_load_state("networkidle")
            await shoot(page, f"{REVIEW_BASE}/dashboard", "review_dashboard")
        except Exception as e:
            print(f"  register/login failed: {e}; falling back")

        # Try to capture the review form. Need a question id; pick the first
        # available batch + first question.
        try:
            # find any pending question link from the dashboard
            await page.goto(f"{REVIEW_BASE}/dashboard", wait_until="networkidle")
            await page.wait_for_timeout(500)
            link = await page.query_selector('a[href*="/review/"]')
            if link:
                href = await link.get_attribute("href")
                review_url = f"{REVIEW_BASE}{href}" if href.startswith("/") else href
                await shoot(page, review_url, "review_form")
            else:
                # last-resort: visit a known route and capture whatever loads
                await shoot(page, f"{REVIEW_BASE}/dashboard", "review_form")
        except Exception as e:
            print(f"  review form capture failed: {e}")

        # Completion screen — try /complete or just dashboard if not present
        try:
            await page.goto(f"{REVIEW_BASE}/complete", wait_until="networkidle")
            await page.wait_for_timeout(500)
            await shoot(page, f"{REVIEW_BASE}/complete", "review_complete")
        except Exception:
            pass

        # Dashboard
        await shoot(page, f"{DASH_BASE}/", "dashboard_phases")

        # HF dataset card preview — render Markdown via a simple Python-rendered
        # HTML page so we can screenshot the README content
        hf_card = (ROOT / "docs" / "huggingface" / "DATASET_CARD.md").read_text()
        # Strip yaml front matter for cleaner display
        if hf_card.startswith("---"):
            _, _, hf_card = hf_card.partition("---\n")[2].partition("---\n")
        # Make a minimal styled HTML page from the markdown
        try:
            import markdown  # type: ignore
            body = markdown.markdown(hf_card, extensions=["tables", "fenced_code"])
        except ImportError:
            body = "<pre>" + hf_card.replace("<", "&lt;") + "</pre>"
        html = f"""<!doctype html><html><head><meta charset='utf-8'><style>
body {{ font-family: -apple-system, system-ui, 'Segoe UI', Helvetica, Arial, sans-serif;
       max-width: 880px; margin: 36px auto; padding: 0 24px; color: #1f2937; line-height: 1.55; }}
h1 {{ border-bottom: 2px solid #e5e7eb; padding-bottom: 8px; }}
h2 {{ border-bottom: 1px solid #e5e7eb; padding-bottom: 4px; margin-top: 28px; }}
table {{ border-collapse: collapse; }} th, td {{ border: 1px solid #d1d5db; padding: 5px 9px; }}
th {{ background: #f3f4f6; }} code {{ background: #f3f4f6; padding: 1px 5px; border-radius: 3px; }}
pre {{ background: #f3f4f6; padding: 10px; border-radius: 6px; overflow-x: auto; }}
.huggingface-banner {{ background: linear-gradient(90deg, #fcd34d, #fbbf24); padding: 14px 18px;
  border-radius: 8px; margin-bottom: 18px; font-weight: 600; }}
</style></head><body>
<div class="huggingface-banner">huggingface.co/datasets/oenobench/oenobench</div>
{body}
</body></html>"""
        # write to a tempfile and screenshot
        tmp = OUT.parent / "hf_preview.html"
        tmp.write_text(html)
        await page.goto("file://" + str(tmp), wait_until="networkidle")
        await page.wait_for_timeout(500)
        await page.screenshot(path=str(OUT / "huggingface_preview.png"), full_page=False)
        print(f"  wrote {(OUT / 'huggingface_preview.png').relative_to(ROOT)}")

        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
