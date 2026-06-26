"""Pure-Python field parsing — no network, fully unit-testable.

Turns a raw "card" (the visible text of a listing tile plus its detail-page
link) into a normalised listing dict. Also parses JSON-LD blocks, which several
of these agency sites embed and which are the most reliable signal when present.
"""
from __future__ import annotations

import json
import re
from datetime import date, datetime

# ---------------------------------------------------------------------------
# Regexes
# ---------------------------------------------------------------------------
_AREA_RE = re.compile(
    r"([\d][\d,]*(?:\.\d+)?)\s*(?:m²|m2|sqm|sq\.?\s*m|square\s*met)", re.I
)
_AREA_LABELLED_RE = re.compile(
    r"(?:net\s+lettable|nla|floor\s*area|total\s*area|building\s*area|warehouse)"
    r"[^\d]{0,20}([\d][\d,]*(?:\.\d+)?)\s*(?:m²|m2|sqm|sq)",
    re.I,
)
_RENT_LINE_RE = re.compile(r"^.*\$.*$", re.M)
_GRADE_RE = re.compile(r"\b([ABC])[\s\-]*grade\b|\bgrade[\s\-]*([ABC])\b", re.I)
_DATE_LISTED_RE = re.compile(
    r"(?:listed|date\s*listed|available)\s*[:\-]?\s*"
    r"(\d{1,2}[\/\-\s][A-Za-z0-9]{2,9}[\/\-\s]\d{2,4})",
    re.I,
)

# Feature keywords used to harvest "property attributes" from card text.
_ATTRIBUTE_KEYWORDS = [
    "stud", "roller door", "container", "canopy", "yard", "hardstand",
    "three phase", "3 phase", "mezzanine", "office", "dock", "loading",
    "ablution", "parking", "car park", "sprinkler", "gantry", "crane",
    "seismic", "nbs", "high stud", "drive through", "drive-through",
    "awning", "forecourt", "fenced", "secure", "motorway", "cool store",
    "coolstore", "freezer", "showroom",
]

_SUFFIXES = (
    "road", "rd", "street", "st", "avenue", "ave", "drive", "dr", "place",
    "pl", "way", "lane", "ln", "crescent", "cres", "highway", "hwy", "close",
    "court", "ct", "terrace", "parade", "quay", "boulevard", "blvd", "grove",
)


def _clean_num(s: str) -> float | None:
    try:
        return float(s.replace(",", ""))
    except (ValueError, AttributeError):
        return None


def parse_area(text: str) -> tuple[float | None, str | None]:
    """Return (sqm, display). Prefer an explicitly labelled floor/NLA figure."""
    m = _AREA_LABELLED_RE.search(text)
    if not m:
        m = _AREA_RE.search(text)
    if not m:
        return None, None
    val = _clean_num(m.group(1))
    if val is None or val <= 0:
        return None, None
    return val, f"{val:,.0f} m²"


def parse_rent(text: str) -> str | None:
    """Return the most rent-looking line (one containing a $ amount)."""
    best = None
    for line in _RENT_LINE_RE.findall(text):
        line = line.strip()
        if not line or len(line) > 120:
            continue
        score = 0
        low = line.lower()
        if "$" in line:
            score += 2
        if any(k in low for k in ("pa", "p.a", "per annum", "annum", "sqm", "/m", "net", "gst", "rent")):
            score += 2
        if any(k in low for k in ("price", "sale", "buy", "auction")):
            score -= 3
        if score > 0 and (best is None or score > best[0]):
            best = (score, line)
    return best[1] if best else None


def parse_grade(text: str) -> str | None:
    m = _GRADE_RE.search(text)
    if not m:
        return None
    g = (m.group(1) or m.group(2) or "").upper()
    return f"{g}-Grade" if g else None


def parse_attributes(text: str) -> list[str]:
    low = text.lower()
    found = []
    for kw in _ATTRIBUTE_KEYWORDS:
        if kw in low and kw not in (f.lower() for f in found):
            found.append(kw.title())
    # de-duplicate near-equivalents
    out, seen = [], set()
    for f in found:
        key = f.lower().replace("-", " ")
        if key not in seen:
            seen.add(key)
            out.append(f)
    return out[:8]


def parse_date_listed(text: str) -> str | None:
    m = _DATE_LISTED_RE.search(text)
    if not m:
        return None
    raw = m.group(1).strip()
    for fmt in ("%d/%m/%Y", "%d/%m/%y", "%d %B %Y", "%d %b %Y", "%d-%m-%Y"):
        try:
            return datetime.strptime(raw, fmt).date().isoformat()
        except ValueError:
            continue
    return None


def parse_address_suburb(title: str, text: str) -> tuple[str | None, str | None]:
    """Best-effort split of a NZ commercial address into (address, suburb)."""
    candidate = (title or "").strip()
    # The first non-empty line of the card is usually the address/headline.
    if not candidate:
        for line in text.splitlines():
            line = line.strip()
            if line and any(c.isdigit() for c in line):
                candidate = line
                break
    if not candidate:
        return None, None
    candidate = re.sub(r"\s+", " ", candidate).strip(" ,-")
    parts = [p.strip() for p in candidate.split(",") if p.strip()]
    suburb = None
    if len(parts) >= 2:
        # Drop a trailing "Auckland" / region/postcode token to expose the suburb.
        tail = [p for p in parts if p.lower() not in ("auckland", "new zealand", "nz")]
        tail = [p for p in tail if not re.fullmatch(r"\d{3,4}", p)]
        if len(tail) >= 2:
            suburb = tail[-1]
    address = parts[0] if parts else candidate
    return address or None, suburb


def looks_like_listing(card: dict) -> bool:
    """Filter out nav/footer/promo anchors that slipped through."""
    text = (card.get("text") or "")
    title = (card.get("title") or "")
    blob = f"{title}\n{text}"
    low = blob.lower()
    if len(blob.strip()) < 8:
        return False
    has_addr = bool(re.search(r"\d+\s*[A-Za-z]", title)) or any(
        s in low for s in (" road", " rd", " street", " st ", " avenue", " drive", " place", " way")
    )
    has_signal = bool(_AREA_RE.search(blob)) or "$" in blob or has_addr
    junk = ("subscribe", "newsletter", "cookie", "privacy policy", "sign in", "log in")
    if any(j in low for j in junk):
        return False
    return has_signal


def normalise_card(card: dict, source_name: str) -> dict | None:
    """Turn a raw extracted card into the dashboard's normalised schema."""
    if not looks_like_listing(card):
        return None
    text = card.get("text") or ""
    title = card.get("title") or ""
    blob = f"{title}\n{text}"
    address, suburb = parse_address_suburb(title, text)
    area_sqm, area_display = parse_area(blob)
    return {
        "source": source_name,
        "title": (title or address or "").strip()[:160] or None,
        "address": address,
        "suburb": suburb,
        "grade": parse_grade(blob),
        "area_sqm": area_sqm,
        "area_display": area_display,
        "rent": parse_rent(blob),
        "date_listed": parse_date_listed(blob),
        "attributes": parse_attributes(blob),
        "owner": None,  # landlords are rarely published; populated from JSON-LD if available
        "url": card.get("url"),
    }


# ---------------------------------------------------------------------------
# JSON-LD
# ---------------------------------------------------------------------------
def parse_jsonld_blocks(blocks: list[str], source_name: str) -> list[dict]:
    out = []
    for raw in blocks:
        try:
            data = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            continue
        for node in _iter_jsonld_nodes(data):
            listing = _jsonld_node_to_listing(node, source_name)
            if listing:
                out.append(listing)
    return out


def _iter_jsonld_nodes(data):
    if isinstance(data, list):
        for d in data:
            yield from _iter_jsonld_nodes(d)
    elif isinstance(data, dict):
        if "@graph" in data:
            yield from _iter_jsonld_nodes(data["@graph"])
        yield data


_WANTED_TYPES = {
    "product", "offer", "place", "residence", "apartment", "house",
    "realestatelisting", "singlefamilyresidence", "commercialproperty",
    "accommodation", "lodgingbusiness",
}


def _jsonld_node_to_listing(node: dict, source_name: str) -> dict | None:
    t = node.get("@type")
    types = {x.lower() for x in (t if isinstance(t, list) else [t]) if isinstance(x, str)}
    if not types & _WANTED_TYPES:
        return None
    name = node.get("name") or ""
    url = node.get("url") or node.get("@id")
    addr = node.get("address")
    address_str, suburb = None, None
    if isinstance(addr, dict):
        address_str = addr.get("streetAddress") or name
        suburb = addr.get("addressLocality") or addr.get("addressRegion")
    elif isinstance(addr, str):
        address_str = addr
    blob = json.dumps(node)
    area_sqm, area_display = parse_area(blob)
    if not (name or address_str):
        return None
    return {
        "source": source_name,
        "title": (name or address_str or "")[:160] or None,
        "address": address_str or name,
        "suburb": suburb,
        "grade": parse_grade(blob),
        "area_sqm": area_sqm,
        "area_display": area_display,
        "rent": parse_rent(blob),
        "date_listed": node.get("datePosted") or node.get("availabilityStarts"),
        "attributes": parse_attributes(blob),
        "owner": _jsonld_owner(node),
        "url": url,
    }


def _jsonld_owner(node: dict) -> str | None:
    for key in ("owner", "landlord", "provider", "seller", "offeredBy"):
        v = node.get(key)
        if isinstance(v, dict) and v.get("name"):
            return v["name"]
        if isinstance(v, str):
            return v
    return None


# ---------------------------------------------------------------------------
# Cross-run helpers
# ---------------------------------------------------------------------------
def listing_key(listing: dict) -> str:
    """Stable identity for a listing across days (URL first, else addr+source)."""
    url = (listing.get("url") or "").split("?")[0].rstrip("/")
    if url:
        return url
    return f"{listing.get('source')}|{(listing.get('address') or '').lower().strip()}"


def apply_history(listing: dict, history: dict, today: date) -> dict:
    """Stamp first_seen and compute days_on_market.

    Uses the site's published listing date when available; otherwise falls back
    to the first date this scraper observed the listing, so the figure accrues
    over time even for sources that don't publish a date.
    """
    key = listing_key(listing)
    first_seen = history.get(key, {}).get("first_seen", today.isoformat())
    listing["first_seen"] = first_seen
    basis = listing.get("date_listed") or first_seen
    try:
        d0 = datetime.strptime(basis[:10], "%Y-%m-%d").date()
        listing["days_on_market"] = max((today - d0).days, 0)
    except (ValueError, TypeError):
        listing["days_on_market"] = None
    return listing
