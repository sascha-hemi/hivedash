"""SQLite has no timezone-aware storage - a value written as tz-aware comes back naive on read,
so every timestamp stored in or compared against the DB in this app is naive-but-implicitly-UTC.
Use utcnow() instead of datetime.now(timezone.utc) anywhere that touches a DB column."""
from __future__ import annotations

from datetime import datetime, timezone


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)
