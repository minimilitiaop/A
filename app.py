#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Alphaporno web frontend
Ported from Lululla & PCD's enigma2 plugin
Scraper regexes preserved from original; UI replaced with Flask + HTML.
"""

import html as html_conv
import re
import unicodedata
from urllib.parse import quote

import requests
from flask import Flask, jsonify, render_template, request

app = Flask(__name__)

BASE = "https://www.alphaporno.com"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}

SECTIONS = {
    "top":       f"{BASE}/top-rated/",
    "popular":   f"{BASE}/most-popular/",
    "longest":   f"{BASE}/longest/",
    "channels":  f"{BASE}/channels/",
    "categories": f"{BASE}/categories/",
    "search":    f"{BASE}/search/?q=",
}


# ---------------------------------------------------------------------
# UTILS (ported from plugin)
# ---------------------------------------------------------------------
def normalize(title: str) -> str:
    try:
        return "".join(
            c for c in unicodedata.normalize("NFKD", title)
            if unicodedata.category(c) != "Mn"
        )
    except Exception:
        return html_conv.unescape(title)


def fetch(url: str) -> str:
    r = requests.get(url, headers=HEADERS, timeout=20, verify=False)
    r.raise_for_status()
    return r.text


def strip_tags(s: str) -> str:
    return re.sub(r"<[^>]+>", "", s).strip()


# ---------------------------------------------------------------------
# SCRAPERS — regex carried over from plugin, where still valid
# ---------------------------------------------------------------------
def parse_video_cards(content: str):
    """Top-rated / popular / longest / search result pages."""
    # plugin used: <a itemprop="url" href="(.*?)".*?src="(.*?)" alt="(.*?)"
    pattern = re.compile(
        r'<a\s+itemprop="url"\s+href="(.*?)".*?src="(.*?)"\s+alt="(.*?)"',
        re.DOTALL,
    )
    out = []
    for url, pic, name in pattern.findall(content):
        out.append({
            "name": html_conv.unescape(normalize(name)),
            "url": url,
            "thumb": pic,
        })
    return out


def parse_channels(content: str):
    """Channels page — plugin regex."""
    pattern = re.compile(
        r'<li class="thumb channel-thumb">.*?a href="(.*?)" title="(.*?)".*?img src="(.*?)"',
        re.DOTALL,
    )
    return [
        {
            "name": html_conv.unescape(normalize(name)),
            "url": url,
            "thumb": pic,
        }
        for url, name, pic in pattern.findall(content)
    ]


def parse_categories(content: str):
    """Categories page — plugin extracted the Categories ul block first."""
    n1 = content.find("span>Categories</span>")
    n2 = content.find("</ul>", n1)
    if n1 < 0 or n2 < 0:
        return []
    block = content[n1:n2]
    pattern = re.compile(r'<a href="(.*?)" title="(.*?)"')
    return [
        {"name": html_conv.unescape(normalize(name)), "url": url}
        for url, name in pattern.findall(block)
    ]


def parse_video_page(content: str):
    """Video page — plugin regex: <source src="..." title="...">"""
    pattern = re.compile(r'<source\s+src="(.*?)"\s+title="(.*?)"', re.DOTALL)
    return [
        {"name": html_conv.unescape(normalize(name)), "url": url}
        for url, name in pattern.findall(content)
    ]


def parse_pages(content: str, base_url: str):
    """Discover pagination — plugin hardcoded 1..100; we read real pages."""
    # try to find pagination links; fall back to 1..100 if absent
    pattern = re.compile(rf'{re.escape(base_url)}/(\d+)', re.DOTALL)
    nums = sorted({int(n) for n in pattern.findall(content)})
    if not nums:
        return list(range(1, 21))  # modest fallback
    return list(range(1, max(nums) + 1))


# ---------------------------------------------------------------------
# ROUTES
# ---------------------------------------------------------------------
@app.route("/")
def index():
    return render_template("index.html", sections=SECTIONS)


@app.route("/api/section/<name>")
def api_section(name):
    if name not in SECTIONS:
        return jsonify(error="unknown section"), 404
    url = SECTIONS[name]
    try:
        content = fetch(url)
    except Exception as e:
        return jsonify(error=str(e)), 502

    if name == "channels":
        items = parse_channels(content)
    elif name == "categories":
        items = parse_categories(content)
    else:
        items = parse_video_cards(content)

    return jsonify(section=name, items=items)


@app.route("/api/section/<name>/page/<int:page>")
def api_section_page(name, page):
    if name not in SECTIONS:
        return jsonify(error="unknown section"), 404
    url = f"{SECTIONS[name].rstrip('/')}/{page}"
    try:
        content = fetch(url)
    except Exception as e:
        return jsonify(error=str(e)), 502

    if name == "channels":
        items = parse_channels(content)
    elif name == "categories":
        items = parse_categories(content)
    else:
        items = parse_video_cards(content)

    return jsonify(section=name, page=page, items=items)


@app.route("/api/search")
def api_search():
    q = (request.args.get("q") or "").strip()
    if not q:
        return jsonify(items=[])
    url = SECTIONS["search"] + quote(q)
    try:
        content = fetch(url)
    except Exception as e:
        return jsonify(error=str(e)), 502
    return jsonify(query=q, items=parse_video_cards(content))


@app.route("/api/video")
def api_video():
    """Return playable <source> entries for a video page."""
    url = request.args.get("url", "").strip()
    if not url.startswith(BASE):
        return jsonify(error="url must be on alphaporno.com"), 400
    try:
        content = fetch(url)
    except Exception as e:
        return jsonify(error=str(e)), 502
    return jsonify(url=url, sources=parse_video_page(content))


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)
