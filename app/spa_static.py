"""Serves the compiled Angular SPA with client-side-routing fallback.

Plain StaticFiles(html=True) 404s for a direct load of e.g. /admin/users, since no such file
exists on disk - only Angular's in-browser router knows that route. This subclass falls back to
index.html for any 404 that isn't under /api/, so a real missing asset (a typo'd JS/CSS filename)
still 404s correctly - only the *fallback* target changes, not the initial lookup.
"""
from __future__ import annotations

from starlette.exceptions import HTTPException
from starlette.responses import Response
from starlette.staticfiles import StaticFiles
from starlette.types import Scope


class SPAStaticFiles(StaticFiles):
    async def get_response(self, path: str, scope: Scope) -> Response:
        try:
            return await super().get_response(path, scope)
        except HTTPException as exc:
            # Only fall back for a client-side route (no file extension, e.g. /admin/users) -
            # a missing real asset (/foo.js, /favicon.ico) must still 404, not silently become HTML.
            last_segment = path.rsplit("/", 1)[-1]
            is_client_route = exc.status_code == 404 and not path.startswith("api/") and "." not in last_segment
            if is_client_route:
                return await super().get_response("index.html", scope)
            raise
