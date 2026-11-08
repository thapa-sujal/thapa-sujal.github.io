#!/usr/bin/env python3
"""
build_live.py — fetches recently-read books from Goodreads and recent films
from Letterboxd, then writes live-data.js for the portfolio site.

Run manually: python3 build_live.py
The deployed site also refreshes this file automatically through GitHub Actions.
"""

import re
import json
import ssl
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from html import unescape

# macOS ships Python without the system CA bundle wired up;
# create an unverified context for these personal-data requests.
_ctx = ssl._create_unverified_context()

GOODREADS_WIDGET = "https://www.goodreads.com/review/custom_widget/77176951.Suzal"
LETTERBOXD_RSS = "https://letterboxd.com/Suzal007/rss/"
OUTPUT_FILE    = "live-data.js"
MAX_BOOKS      = 2
MAX_FILMS      = 2


def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=15, context=_ctx) as r:
        return r.read().decode("utf-8", errors="replace")


def strip_namespaces(xml_text):
    """Remove xmlns declarations and namespace prefixes so ElementTree parses cleanly."""
    xml_text = re.sub(r'\s+xmlns(?::\w+)?="[^"]*"', '', xml_text)
    xml_text = re.sub(r'<(/?)(\w+):(\w+)', r'<\1\3', xml_text)
    return xml_text


def tag_text(item, *names):
    """Return text of the first matching tag name (case-insensitive local name)."""
    name_set = {n.lower() for n in names}
    for child in item:
        local = (child.tag.split("}")[-1] if "}" in child.tag else child.tag).lower()
        if local in name_set:
            return (child.text or "").strip()
    return ""


def goodreads_widget_url():
    """Build a fresh URL for the newest additions to the public read shelf."""
    params = {
        "cover_position": "left",
        "cover_size": "medium",
        "num_books": MAX_BOOKS,
        "order": "d",
        "shelf": "read",
        "show_author": 1,
        "show_rating": 1,
        "sort": "date_added",
        # Goodreads caches widget responses by widget_id. A fresh value prevents
        # an old shelf snapshot from being served to the scheduled updater.
        "widget_id": time.time_ns(),
    }
    return f"{GOODREADS_WIDGET}?{urllib.parse.urlencode(params)}"


def parse_goodreads(widget_text):
    """Parse the newest books from Goodreads' public read-shelf widget."""
    html_text = (widget_text
                 .replace(r"\n", "\n")
                 .replace(r'\"', '"')
                 .replace(r"\/", "/")
                 .replace(r"\'", "'"))

    books = []
    cards = re.split(r'<div class="gr_custom_each_container_[^"]*">', html_text)
    for card in cards[1:]:
        book = re.search(
            r'<a title="(.*?)"[^>]+href="([^"]+)"><img[^>]+src="([^"]+)"',
            card,
            re.S,
        )
        author_match = re.search(
            r'<div class="gr_custom_author_[^"]*">\s*by\s*<a[^>]*>(.*?)</a>',
            card,
            re.S,
        )
        if not book or not author_match:
            continue

        title, link, cover = book.groups()
        author = re.sub(r"<[^>]+>", "", author_match.group(1))
        cover = re.sub(r"\._S[XY]\d+_", "._SY475_", cover)
        rating = str(card.count("gr_flat_red_star_active.png"))

        books.append({
            "title":  unescape(title),
            "author": unescape(author),
            "cover":  cover,
            "url":    unescape(link),
            "rating": rating if rating != "0" else "",
        })

        if len(books) >= MAX_BOOKS:
            break

    return books


def parse_letterboxd(xml_text):
    xml_text = strip_namespaces(xml_text)
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as e:
        print(f"  ✗ Letterboxd XML parse error: {e}")
        return []

    films = []
    for item in root.iter("item"):
        title  = tag_text(item, "filmtitle") or tag_text(item, "title")
        year   = tag_text(item, "filmyear")
        rating = tag_text(item, "memberrating")
        link   = tag_text(item, "link")

        # Poster: check tmdb/letterboxd poster attribute, then description img
        poster = ""
        for child in item:
            local = (child.tag.split("}")[-1] if "}" in child.tag else child.tag).lower()
            if local == "poster" and child.get("url"):
                poster = child.get("url")
                break
        if not poster:
            desc = tag_text(item, "description")
            m = re.search(r'<img[^>]+src="([^"]+)"', desc)
            if m:
                poster = m.group(1)

        # Strip rating suffix from raw title if filmtitle was unavailable
        title_clean = re.sub(r",?\s*\d{4}.*$", "", title).strip() or title

        if not title_clean:
            continue

        films.append({
            "title":  unescape(title_clean),
            "year":   year,
            "rating": rating,
            "poster": poster,
            "url":    link,
        })

        if len(films) >= MAX_FILMS:
            break

    return films


def build():
    print("Fetching Goodreads recently-read…")
    try:
        books = parse_goodreads(fetch(goodreads_widget_url()))
        if not books:
            raise ValueError("read shelf returned no books")
        print(f"  ✓ {len(books)} book(s)")
    except Exception as e:
        print(f"  ✗ Goodreads failed: {e}")
        raise SystemExit("Library data was left unchanged.") from e

    print("Fetching Letterboxd recent films…")
    try:
        films = parse_letterboxd(fetch(LETTERBOXD_RSS))
        if not films:
            raise ValueError("feed returned no films")
        print(f"  ✓ {len(films)} film(s)")
    except Exception as e:
        print(f"  ✗ Letterboxd failed: {e}")
        raise SystemExit("Library data was left unchanged.") from e

    js_data = json.dumps({"books": books, "films": films}, indent=2, ensure_ascii=False)

    output = f"""// Auto-generated from Goodreads and Letterboxd — do not edit directly.
// Refreshed automatically by .github/workflows/update-library.yml.

const LIVE_DATA = {js_data};
"""

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write(output)

    print(f"\n✓ Wrote {len(books)} book(s), {len(films)} film(s) → {OUTPUT_FILE}")


if __name__ == "__main__":
    build()
