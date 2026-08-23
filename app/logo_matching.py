"""Pure logo-matching logic - no DB/ORM import, mirrors app.merge's testability philosophy.

Takes plain data (LogoCandidate, not the Logo ORM model) so this stays unit-testable in isolation,
exactly like app/merge.py and app/dashboard_view.py.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

# Below this length, a keyword matches far too much by pure coincidence to be trustworthy for an
# unreviewed/automatic assignment - e.g. "api" or "ide" turning up inside an unrelated domain
# ("provider.example" contains "ide"). Chosen so real short app names ("plex", 4 chars) still work.
_MIN_KEYWORD_LENGTH = 4

_NON_ALNUM = re.compile(r"[^a-z0-9]")


def _normalize(s: str) -> str:
    """Strips separators before comparing, so a catalog slug like "home-assistant" still matches
    a real-world container/host name like "homeassistant" - services rarely agree on hyphens vs.
    no separator at all."""
    return _NON_ALNUM.sub("", s.lower())


@dataclass(frozen=True)
class LogoCandidate:
    id: int
    keywords: list[str]


def match_logo(candidates: list[str], logos: list[LogoCandidate]) -> int | None:
    """Case-insensitive, separator-insensitive substring match of each logo's keywords against
    the candidate strings.

    The longest matching keyword wins (so a specific "plex" keyword beats a generic "media"
    keyword matching the same string); ties are broken by the lowest logo id, so the result is
    deterministic regardless of iteration order.
    """
    haystacks = [_normalize(c) for c in candidates if c]
    best: tuple[int, int] | None = None  # (-len(longest matching keyword), logo.id) - lowest wins

    for logo in logos:
        longest_match: int | None = None
        for keyword in logo.keywords:
            keyword = _normalize(keyword)
            if len(keyword) < _MIN_KEYWORD_LENGTH:
                continue
            if any(keyword in haystack for haystack in haystacks):
                if longest_match is None or len(keyword) > longest_match:
                    longest_match = len(keyword)
        if longest_match is not None:
            candidate_key = (-longest_match, logo.id)
            if best is None or candidate_key < best:
                best = candidate_key

    return best[1] if best is not None else None
