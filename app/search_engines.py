"""Static registry of external search engines the dashboard's search bar can launch a query
to (see frontend `search/` for the component). Deliberately just a label + URL template with
a `{query}` placeholder per engine - adding a new provider is one more dict entry, never new
code. Kept in its own module (mirrors app/logo_matching.py) so it stays import-light and easy
to unit test without pulling in FastAPI/SQLAlchemy."""
from __future__ import annotations

SEARCH_ENGINES: dict[str, dict[str, str]] = {
    "google": {"label": "Google", "url_template": "https://www.google.com/search?q={query}"},
    "bing": {"label": "Bing", "url_template": "https://www.bing.com/search?q={query}"},
    "duckduckgo": {"label": "DuckDuckGo", "url_template": "https://duckduckgo.com/?q={query}"},
    "startpage": {"label": "Startpage", "url_template": "https://www.startpage.com/sp/search?query={query}"},
    "brave": {"label": "Brave Search", "url_template": "https://search.brave.com/search?q={query}"},
    "ecosia": {"label": "Ecosia", "url_template": "https://www.ecosia.org/search?q={query}"},
    "kagi": {"label": "Kagi", "url_template": "https://kagi.com/search?q={query}"},
    "perplexity": {"label": "Perplexity", "url_template": "https://www.perplexity.ai/search?q={query}"},
}

DEFAULT_SEARCH_ENGINE = "google"


def resolve_search_engine(key: str | None) -> str:
    """Falls back to the default for None/unknown - never lets a stale stored value or a
    typo'd SEARCH_ENGINE env var break the search bar."""
    if key and key in SEARCH_ENGINES:
        return key
    return DEFAULT_SEARCH_ENGINE
