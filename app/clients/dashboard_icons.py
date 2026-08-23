"""Client for the dashboard-icons catalog (github.com/homarr-labs/dashboard-icons, Apache-2.0).

Two ways this gets used:
1. An admin explicitly searches/imports one icon via the Logos admin page.
2. The poll loop (app/db/repository.py) calls find_best_slug()/fetch_icon() automatically for any
   service that has no local Logo match yet - gated by settings.logo_catalog_auto_import (default
   on). This is a deliberate, best-effort exception to "polling never needs internet access": a
   catalog miss or a network failure here never breaks the poll, it just leaves logo_id unset for
   another attempt next cycle (same "sticky but self-healing" idiom as local matching).
"""
from __future__ import annotations

import re

import httpx

METADATA_URL = "https://raw.githubusercontent.com/homarr-labs/dashboard-icons/main/metadata.json"
_ICON_URL = "https://raw.githubusercontent.com/homarr-labs/dashboard-icons/main/{base}/{slug}.{ext}"

# Same rationale as app.logo_matching._MIN_KEYWORD_LENGTH - only applied in find_best_slug()
# (the *unreviewed*, automatic path). search_catalog() is for a human browsing/confirming results,
# so a short query there (e.g. "r" for the R language) is fine and stays unrestricted.
_MIN_KEYWORD_LENGTH = 4

_NON_ALNUM = re.compile(r"[^a-z0-9]")


def _normalize(s: str) -> str:
    """Strips separators before comparing - a slug like "home-assistant" should still match a
    real container/host name like "homeassistant" (see app.logo_matching._normalize)."""
    return _NON_ALNUM.sub("", s.lower())

_EXTENSION_BY_BASE = {"svg": "svg", "png": "png", "webp": "webp"}
_CONTENT_TYPE_BY_EXTENSION = {
    "svg": "image/svg+xml",
    "png": "image/png",
    "webp": "image/webp",
}

_cached_metadata: dict | None = None


def _icon_url(slug: str, base: str) -> str:
    ext = _EXTENSION_BY_BASE.get(base, "svg")
    return _ICON_URL.format(base=base, slug=slug, ext=ext)


# Deliberately NOT trying to auto-pick a "light"/"dark" color variant from a catalog entry's
# `colors` metadata: it's community-contributed and the convention isn't applied consistently -
# for one icon "dark" is the visible-on-white variant, for another it's the opposite (confirmed
# by hand: karakeep's "dark" key is black/visible-on-white, proxmox-backup-server's "dark" key is
# white/invisible-on-white). Guessing wrong silently replaces a good default icon with a bad one.
# Just fetching the plain requested slug is right far more often (most icons are full-color, not
# monochrome) - the frontend's white avatar backing plus the search page's matching preview
# background (see admin-logos.html) let an admin see and avoid/replace the rare bad case instead.


async def _load_metadata() -> dict:
    global _cached_metadata
    if _cached_metadata is None:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(METADATA_URL)
            resp.raise_for_status()
            _cached_metadata = resp.json()
    return _cached_metadata


async def search_catalog(query: str, limit: int = 24) -> list[dict]:
    query = _normalize(query)
    if not query:
        return []
    metadata = await _load_metadata()

    results = []
    for slug, info in metadata.items():
        aliases = info.get("aliases", [])
        haystacks = [_normalize(slug), *[_normalize(a) for a in aliases]]
        if any(query in haystack for haystack in haystacks):
            base = info.get("base", "svg")
            results.append({"slug": slug, "aliases": aliases, "preview_url": _icon_url(slug, base)})
            if len(results) >= limit:
                break
    return results


async def find_best_slug(candidates: list[str]) -> str | None:
    """Same "longest matching keyword wins" rule as app.logo_matching.match_logo, but against the
    catalog's slug+aliases instead of the local Logo library (kept separate rather than sharing
    code with that pure module, since this one needs network I/O for the metadata and ties break
    alphabetically by slug rather than by an integer id)."""
    haystacks = [_normalize(c) for c in candidates if c]
    if not haystacks:
        return None
    metadata = await _load_metadata()

    best: tuple[int, str] | None = None  # (-len(longest matching keyword), slug) - lowest wins
    for slug, info in metadata.items():
        longest_match: int | None = None
        for keyword in [slug, *info.get("aliases", [])]:
            keyword = _normalize(keyword)
            if len(keyword) < _MIN_KEYWORD_LENGTH:
                continue
            if any(keyword in haystack for haystack in haystacks):
                if longest_match is None or len(keyword) > longest_match:
                    longest_match = len(keyword)
        if longest_match is not None:
            candidate_key = (-longest_match, slug)
            if best is None or candidate_key < best:
                best = candidate_key

    return best[1] if best is not None else None


async def fetch_icon(slug: str) -> tuple[bytes, str, list[str]]:
    """Returns (image_bytes, content_type, aliases) for a catalog slug."""
    metadata = await _load_metadata()
    info = metadata.get(slug)
    if info is None:
        raise ValueError(f"unknown dashboard-icons slug: {slug}")

    base = info.get("base", "svg")
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.get(_icon_url(slug, base))
        resp.raise_for_status()

    content_type = _CONTENT_TYPE_BY_EXTENSION.get(_EXTENSION_BY_BASE.get(base, "svg"), "application/octet-stream")
    return resp.content, content_type, info.get("aliases", [])
