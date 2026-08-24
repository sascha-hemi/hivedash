"""Update-check against GitHub Releases - "anzeige only": this never downloads or applies
anything, it just tells an admin a newer version exists so they can `docker compose pull && up
-d` themselves. Best-effort throughout: a network failure, rate limit, or a repo with no
releases yet must never break startup or the dashboard - it just means "can't tell right now"."""
from __future__ import annotations

import httpx

GITHUB_REPO = "sascha-hemi/hivedash"
GITHUB_LATEST_RELEASE_API = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"


def parse_version(value: str) -> tuple[int, ...] | None:
    """"v1.2.0" / "1.2.0" -> (1, 2, 0). None for anything not a plain dotted-integer version
    (e.g. "dev", "main", a short commit sha) - those just can't be compared, not "outdated"."""
    stripped = value.strip().lstrip("vV")
    parts = stripped.split(".")
    try:
        return tuple(int(p) for p in parts)
    except ValueError:
        return None


def is_update_available(current: str, latest: str) -> bool | None:
    """None (not True/False) means "can't tell" - e.g. a dev build has no comparable version.
    The frontend must treat None as "no update banner", not as "you're up to date"."""
    current_parsed = parse_version(current)
    latest_parsed = parse_version(latest)
    if current_parsed is None or latest_parsed is None:
        return None
    return latest_parsed > current_parsed


async def fetch_latest_release() -> dict | None:
    """Returns {"tag_name", "html_url"} for the latest GitHub Release, or None on any failure."""
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                GITHUB_LATEST_RELEASE_API, headers={"Accept": "application/vnd.github+json"},
            )
            resp.raise_for_status()
            data = resp.json()
            return {"tag_name": data["tag_name"], "html_url": data["html_url"]}
    except (httpx.HTTPError, KeyError, ValueError, TypeError):
        return None
