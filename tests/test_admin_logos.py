"""Drives the real FastAPI app over an in-process ASGI transport against a temp-file SQLite DB:
logo upload/list/delete, the dangling-reference cleanup on delete, and that image serving is
reachable by any logged-in user (not just admins, unlike the rest of /api/admin/*)."""
import asyncio
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

TMP_DB = tempfile.NamedTemporaryFile(suffix=".db", delete=False).name
os.environ["DATABASE_PATH"] = TMP_DB
os.environ.setdefault("COOKIE_SECURE", "false")

import httpx  # noqa: E402
from sqlalchemy import select  # noqa: E402

from app.db import admin_repository  # noqa: E402
from app.db.engine import get_sessionmaker, init_models  # noqa: E402
from app.db.models import ProxyHost  # noqa: E402
from app.main import app  # noqa: E402

TINY_SVG = b'<svg xmlns="http://www.w3.org/2000/svg"><rect width="1" height="1"/></svg>'


async def main():
    await init_models()
    sessionmaker = get_sessionmaker()

    async with sessionmaker() as session:
        await admin_repository.create_user(
            session, email="admin@test.local", password="correct-horse",
            display_name="Admin", role="admin", dashboard_id=None,
        )
        await admin_repository.create_user(
            session, email="member@test.local", password="hunter2222",
            display_name="Member", role="user", dashboard_id=None,
        )

    transport = httpx.ASGITransport(app=app)

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        await client.post("/api/auth/login", json={"email": "member@test.local", "password": "hunter2222"})
        resp = await client.get("/api/admin/logos")
        assert resp.status_code == 403, resp.text

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/api/auth/login", json={"email": "admin@test.local", "password": "correct-horse"})
        assert resp.status_code == 200, resp.text
        csrf = client.cookies["csrf_token"]

        resp = await client.post(
            "/api/admin/logos",
            data={"name": "Plex", "keywords": "plex, plexmediaserver"},
            files={"file": ("plex.svg", TINY_SVG, "image/svg+xml")},
            headers={"X-CSRF-Token": csrf},
        )
        assert resp.status_code == 201, resp.text
        logo = resp.json()
        assert logo["keywords"] == ["plex", "plexmediaserver"], logo
        logo_id = logo["id"]

        resp = await client.get("/api/admin/logos")
        assert resp.status_code == 200 and len(resp.json()) == 1, resp.text

        resp = await client.get(f"/api/logos/{logo_id}/image")
        assert resp.status_code == 200, resp.text
        assert resp.content == TINY_SVG
        assert resp.headers["content-type"].startswith("image/svg+xml")

        # unsupported content type is rejected
        resp = await client.post(
            "/api/admin/logos",
            data={"name": "Bad", "keywords": ""},
            files={"file": ("bad.txt", b"not an image", "text/plain")},
            headers={"X-CSRF-Token": csrf},
        )
        assert resp.status_code == 400, resp.text

    # a plain logged-in (non-admin) user can still load the image - it's outside admin_router
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        await client.post("/api/auth/login", json={"email": "member@test.local", "password": "hunter2222"})
        resp = await client.get(f"/api/logos/{logo_id}/image")
        assert resp.status_code == 200, resp.text

    # a service referencing the logo, then deleting it must null out the reference, not dangle it
    async with sessionmaker() as session:
        session.add(
            ProxyHost(
                npm_host_id=1, domain_names=["plex.example.com"], forward_scheme="http",
                forward_host="10.0.0.5", forward_port=80, enabled=True, online=True, ssl=False,
                logo_id=logo_id,
            )
        )
        await session.commit()

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        await client.post("/api/auth/login", json={"email": "admin@test.local", "password": "correct-horse"})
        csrf = client.cookies["csrf_token"]
        resp = await client.delete(f"/api/admin/logos/{logo_id}", headers={"X-CSRF-Token": csrf})
        assert resp.status_code == 200, resp.text

        resp = await client.get(f"/api/logos/{logo_id}/image")
        assert resp.status_code == 404, resp.text

    async with sessionmaker() as session:
        row = (await session.execute(select(ProxyHost).where(ProxyHost.npm_host_id == 1))).scalar_one()
        assert row.logo_id is None, "deleting a logo must null out any dangling reference"

    os.remove(TMP_DB)
    print("All admin_logos tests passed.")


asyncio.run(main())
