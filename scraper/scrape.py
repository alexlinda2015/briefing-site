"""Scrape the six Auckland industrial-lease sources with a real headless browser.

Run on GitHub Actions (open internet). Each source is isolated: a failure on one
is recorded as a per-source status and never aborts the run. Outputs:

  data/listings.json   normalised listings + run metadata + per-source status
  data/seen.json       first-seen history (drives days-on-market)
  scraper/debug/*.html raw page HTML per source (uploaded as a CI artifact)

Usage:  python scraper/scrape.py
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
from datetime import date, datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from playwright.async_api import async_playwright

NZ_TZ = ZoneInfo("Pacific/Auckland")

sys.path.insert(0, str(Path(__file__).resolve().parent))
import parse as P  # noqa: E402
from sources import SOURCES  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
DEBUG_DIR = Path(__file__).resolve().parent / "debug"
NAV_TIMEOUT_MS = 60_000
MAX_LOAD_MORE = 4

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

# JS injected into each page to harvest candidate listing cards.
EXTRACT_JS = r"""
(cfg) => {
  const subs = (cfg.detailSubstrings || []).map(s => s.toLowerCase());
  const origin = location.origin;
  const anchors = Array.from(document.querySelectorAll('a[href]'));
  const cards = new Map();
  for (const a of anchors) {
    let href = a.href || '';
    if (!href || href.startsWith('javascript') || href.startsWith('mailto')
        || href.startsWith('tel')) continue;
    const low = href.toLowerCase();
    if (subs.length && !subs.some(s => low.includes(s))) continue;
    // Skip obvious non-listing links.
    if (/\/(about|contact|careers|news|team|people|agents|privacy|terms|login|sitemap)\b/.test(low)) continue;
    const card = a.closest(
      'article, li, .card, [class*="card"], [class*="listing"], [class*="property"], '
      + '[class*="result"], [class*="tile"], [class*="item"]'
    ) || a.parentElement;
    if (!card) continue;
    const text = (card.innerText || '').replace(/ /g, ' ').trim();
    const title = (a.getAttribute('title') || a.getAttribute('aria-label') || a.innerText || '').trim();
    const key = href.split('#')[0];
    if (!cards.has(key)) {
      cards.set(key, { url: href, title, text });
    } else {
      const cur = cards.get(key);
      if (text.length > cur.text.length) cur.text = text;
      if (!cur.title && title) cur.title = title;
    }
  }
  return Array.from(cards.values());
}
"""

JSONLD_JS = """
() => Array.from(document.querySelectorAll('script[type="application/ld+json"]'))
        .map(s => s.textContent)
"""


async def _dismiss_banners(page):
    """Click through common cookie / consent overlays so they don't block content."""
    labels = ["Accept all", "Accept All", "Accept", "I agree", "Agree", "Got it",
              "Allow all", "OK", "Continue", "Close"]
    for label in labels:
        try:
            btn = page.get_by_role("button", name=label, exact=False)
            if await btn.count():
                await btn.first.click(timeout=2500)
                await page.wait_for_timeout(500)
                break
        except Exception:
            continue


async def _auto_scroll(page, rounds=10):
    """Scroll to the bottom repeatedly to trigger lazy-loaded listings."""
    prev_height = 0
    for _ in range(rounds):
        try:
            height = await page.evaluate("document.body.scrollHeight")
            await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            await page.wait_for_timeout(1200)
            if height == prev_height:
                break
            prev_height = height
        except Exception:
            break


async def _click_load_more(page):
    for label in ["Load more", "Show more", "View more", "More results", "Next"]:
        try:
            btn = page.get_by_role("button", name=label, exact=False)
            if await btn.count():
                await btn.first.click(timeout=3000)
                await page.wait_for_timeout(1800)
                return True
            link = page.get_by_role("link", name=label, exact=False)
            if await link.count():
                await link.first.click(timeout=3000)
                await page.wait_for_timeout(1800)
                return True
        except Exception:
            continue
    return False


def _dedupe(listings):
    seen, out = set(), []
    for item in listings:
        key = P.listing_key(item)
        if key in seen:
            continue
        seen.add(key)
        out.append(item)
    return out


async def scrape_source(context, src) -> dict:
    name = src["name"]
    result = {"name": name, "url": src["url"], "color": src["color"],
              "status": "error", "error": None, "count": 0, "listings": []}
    page = await context.new_page()
    page.set_default_timeout(NAV_TIMEOUT_MS)
    try:
        try:
            await page.goto(src["url"], wait_until=src.get("wait_until", "load"),
                            timeout=NAV_TIMEOUT_MS)
        except Exception:
            # networkidle can time out on chatty SPAs; fall back to domcontentloaded.
            await page.goto(src["url"], wait_until="domcontentloaded",
                            timeout=NAV_TIMEOUT_MS)
        await page.wait_for_timeout(2500)
        await _dismiss_banners(page)
        await _auto_scroll(page)
        for _ in range(MAX_LOAD_MORE):
            if not await _click_load_more(page):
                break
            await _auto_scroll(page, rounds=4)

        # Save raw HTML for debugging / parser tuning (artifact, gitignored).
        try:
            DEBUG_DIR.mkdir(parents=True, exist_ok=True)
            html = await page.content()
            (DEBUG_DIR / f"{name.replace(' ', '_').lower()}.html").write_text(
                html, encoding="utf-8")
        except Exception:
            pass

        cfg = {"detailSubstrings": src.get("detail_substrings", [])}
        raw_cards = await page.evaluate(EXTRACT_JS, cfg)
        jsonld_blocks = await page.evaluate(JSONLD_JS)

        listings = []
        for block in P.parse_jsonld_blocks(jsonld_blocks or [], name):
            listings.append(block)
        for card in raw_cards or []:
            norm = P.normalise_card(card, name)
            if norm:
                listings.append(norm)

        listings = _dedupe(listings)
        result["listings"] = listings
        result["count"] = len(listings)
        result["status"] = "ok" if listings else "no-data"
    except Exception as exc:  # noqa: BLE001 - never let one source kill the run
        result["error"] = f"{type(exc).__name__}: {exc}"[:300]
        result["status"] = "error"
    finally:
        await page.close()
    return result


async def run() -> dict:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    history_path = DATA_DIR / "seen.json"
    history = {}
    if history_path.exists():
        try:
            history = json.loads(history_path.read_text())
        except json.JSONDecodeError:
            history = {}

    today = datetime.now(NZ_TZ).date()
    sources_status, all_listings = [], []

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-blink-features=AutomationControlled",
                  "--disable-dev-shm-usage"],
        )
        context = await browser.new_context(
            user_agent=UA,
            locale="en-NZ",
            timezone_id="Pacific/Auckland",
            viewport={"width": 1440, "height": 900},
            extra_http_headers={"Accept-Language": "en-NZ,en;q=0.9"},
        )
        await context.add_init_script(
            "Object.defineProperty(navigator,'webdriver',{get:()=>undefined});")

        for src in SOURCES:
            print(f"[scrape] {src['name']} …", flush=True)
            res = await scrape_source(context, src)
            print(f"[scrape] {src['name']}: {res['status']} ({res['count']})",
                  flush=True)
            for item in res["listings"]:
                P.apply_history(item, history, today)
                all_listings.append(item)
            sources_status.append({k: res[k] for k in
                                   ("name", "url", "color", "status", "error", "count")})

        await browser.close()

    # Refresh first-seen history for every listing observed today.
    for item in all_listings:
        key = P.listing_key(item)
        history.setdefault(key, {})["first_seen"] = item["first_seen"]
        history[key]["last_seen"] = today.isoformat()
    history_path.write_text(json.dumps(history, indent=2), encoding="utf-8")

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "generated_nz": datetime.now(NZ_TZ).strftime("%a %d %b %Y, %I:%M %p NZ"),
        "total": len(all_listings),
        "sources": sources_status,
        "listings": sorted(
            all_listings,
            key=lambda x: (x.get("days_on_market") is None, x.get("days_on_market") or 0),
        ),
    }
    out_path = DATA_DIR / "listings.json"
    out_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False),
                        encoding="utf-8")
    print(f"[scrape] wrote {out_path} — {payload['total']} listings", flush=True)
    return payload


if __name__ == "__main__":
    asyncio.run(run())
