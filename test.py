#!/usr/bin/env python3
"""
PolitePlaywrightScraper
=======================
Scrapes JavaScript‑heavy pages with Playwright, politely, and converts them to Markdown.
"""

import asyncio
import logging
import time
from typing import Dict, Iterable, Optional
from urllib.parse import urljoin, urlparse

from playwright.async_api import async_playwright, TimeoutError as PWTimeout
import markdownify
import urllib.robotparser
import httpx                       # lightweight for HEAD checks, 429 handling

class PolitePlaywrightScraper:
    def __init__(
        self,
        base_url: str,
        delay: float = 3.0,
        user_agent: str = "PolitePlaywrightScraper/1.0 (+you@example.com)",
        nav_timeout: int = 15_000,           # ms
    ):
        self.base_url = base_url.rstrip("/")
        self.delay = delay
        self.ua = user_agent
        self.nav_timeout = nav_timeout

        self._robots = urllib.robotparser.RobotFileParser()
        self._robots.set_url(urljoin(self.base_url, "/robots.txt"))
        try:
            self._robots.read()
        except Exception:
            # treat missing or unreadable robots.txt as allowing everything
            pass

        self._last_request_ts: float = 0.0

        logging.basicConfig(
            level=logging.INFO, format="%(asctime)s  %(levelname)s: %(message)s"
        )

    # ---------- helpers --------------------------------------------------
    async def _respect_delay(self) -> None:
        elapsed = time.time() - self._last_request_ts
        if elapsed < self.delay:
            await asyncio.sleep(self.delay - elapsed)

    def _allowed(self, url: str) -> bool:
        # Custom robots.txt logic: if any User-agent: * block allows all, allow scraping
        import requests
        from urllib.parse import urljoin
        robots_url = urljoin(self.base_url, '/robots.txt')
        try:
            resp = requests.get(robots_url, timeout=5)
            if resp.status_code == 200:
                lines = resp.text.splitlines()
                ua_blocks = []
                current_block = []
                for line in lines:
                    line = line.strip()
                    if line.lower().startswith('user-agent:'):
                        if current_block:
                            ua_blocks.append(current_block)
                        current_block = [line]
                    elif current_block:
                        current_block.append(line)
                if current_block:
                    ua_blocks.append(current_block)
                for block in ua_blocks:
                    if any('user-agent:' in l.lower() and '*' in l for l in block):
                        # If this block has Disallow: with empty value, allow all
                        for l in block:
                            if l.lower().startswith('disallow:') and l.strip().lower() == 'disallow:':
                                return True
                # Fallback to standard parser if no allow-all block found
                return self._robots.can_fetch(self.ua, url)
        except Exception:
            pass
        # If robots.txt can't be read, allow by default
        return True

    async def _fetch_page(self, page, url: str) -> Optional[str]:
        """Return rendered HTML for *url* or None on policy failure."""
        if not self._allowed(url):
            logging.warning("Blocked by robots.txt → %s", url)
            return None

        await self._respect_delay()
        try:
            response = await page.goto(url, timeout=self.nav_timeout, wait_until="load")
        except PWTimeout:
            logging.error("Playwright timeout → %s", url)
            return None
        self._last_request_ts = time.time()

        # If the server responds 429, honor Retry‑After
        if response and response.status == 429:
            retry_after = int(response.headers.get("retry-after", "30"))
            logging.warning("429 Too Many Requests → sleeping %s s", retry_after)
            await asyncio.sleep(retry_after)
            return await self._fetch_page(page, url)        # one retry

        if response and 400 <= response.status < 600 and response.status != 429:
            logging.error("%s response (%s) → %s", response.status, response.status_text(), url)
            return None

        return await page.content()

    # ---------- public API ----------------------------------------------
    async def grab_markdown(self, paths: Iterable[str]) -> Dict[str, str]:
        """Return Markdown for each relative *path* under base_url."""
        results = {}
        async with async_playwright() as pw:
            browser = await pw.firefox.launch(headless=True)
            context = await browser.new_context(user_agent=self.ua)
            page = await context.new_page()

            for path in paths:
                url = urljoin(self.base_url, path)
                html = await self._fetch_page(page, url)
                if html is None:
                    continue
                md = markdownify.markdownify(html, heading_style="ATX")
                results[path] = md.strip()
                logging.info("✓ Converted %s (%d chars)", path, len(md))

            await browser.close()
        return results


def scrape_to_markdown(base_url: str, paths: list, outdir: str = "markdown_out", delay: float = 2.5):
    """
    Scrape the given paths from base_url and save as markdown files in outdir.
    """
    import pathlib
    outdir_path = pathlib.Path(outdir)
    outdir_path.mkdir(parents=True, exist_ok=True)
    scraper = PolitePlaywrightScraper(base_url, delay=delay)

    async def main():
        results = await scraper.grab_markdown(paths)
        for path, md in results.items():
            filename = f"{path.strip('/').replace('/', '_') or 'index'}.md"
            (outdir_path / filename).write_text(md, encoding="utf8")
            print(f"saved → {outdir_path / filename}")
    
    asyncio.run(main())


# ---------------- CLI usage example -------------------------------------
if __name__ == "__main__":
    scrape_to_markdown(
        base_url="https://www.tapaking.com.ph/",
        paths=["/"],
        outdir="markdown_out",
        delay=2.5
    )
    # import argparse, textwrap, pathlib

    # parser = argparse.ArgumentParser(
    #     description="Polite Playwright scraper → Markdown",
    #     formatter_class=argparse.RawDescriptionHelpFormatter,
    #     epilog=textwrap.dedent(
    #         """\
    #         Example:
    #           python scraper.py https://example.org / /about /products
    #         """
    #     ),
    # )
    # parser.add_argument("base", help="Base URL (scheme + domain)")
    # parser.add_argument("paths", nargs="+", help="Relative paths to scrape")
    # parser.add_argument("--delay", type=float, default=2.5, help="Seconds between hits")
    # parser.add_argument("--outdir", default="markdown_out", help="Directory to save .md files")
    # args = parser.parse_args()

    # outdir = pathlib.Path(args.outdir)
    # outdir.mkdir(parents=True, exist_ok=True)

    # scraper = PolitePlaywrightScraper(args.base, delay=args.delay)

    # async def main():
    #     results = await scraper.grab_markdown(args.paths)
    #     for path, md in results.items():
    #         filename = f"{path.strip('/').replace('/', '_') or 'index'}.md"
    #         (outdir / filename).write_text(md, encoding="utf8")
    #         print(f"saved → {outdir / filename}")

    # asyncio.run(main())
