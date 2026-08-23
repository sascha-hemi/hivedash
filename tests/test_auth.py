"""Drives the real FastAPI app (no mocking) over an in-process ASGI transport against a temp-file
SQLite DB: login/logout, session cookie + CSRF double-submit, and role-gated admin routes."""
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

from app.db import admin_repository  # noqa: E402
from app.db.engine import get_sessionmaker, init_models  # noqa: E402
from app.main import app  # noqa: E402


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
        resp = await client.post("/api/auth/login", json={"email": "admin@test.local", "password": "wrong"})
        assert resp.status_code == 401, resp.text

        resp = await client.post("/api/auth/login", json={"email": "admin@test.local", "password": "correct-horse"})
        assert resp.status_code == 200, resp.text
        assert "session" in resp.cookies and "csrf_token" in resp.cookies

        resp = await client.get("/api/auth/me")
        assert resp.status_code == 200, resp.text
        assert resp.json() == {
            "id": resp.json()["id"], "email": "admin@test.local",
            "display_name": "Admin", "role": "admin",
        }

        # read-only admin route needs no CSRF header
        resp = await client.get("/api/admin/users")
        assert resp.status_code == 200, resp.text
        assert {u["email"] for u in resp.json()} == {"admin@test.local", "member@test.local"}

        # mutating admin route without the CSRF header -> rejected
        resp = await client.post("/api/admin/users", json={"email": "x@test.local", "password": "pw"})
        assert resp.status_code == 403, resp.text

        # ... with the header (read back from the cookie jar, like the Angular interceptor would) -> works
        csrf = client.cookies["csrf_token"]
        resp = await client.post(
            "/api/admin/users",
            json={"email": "new@test.local", "password": "pw", "role": "user"},
            headers={"X-CSRF-Token": csrf},
        )
        assert resp.status_code == 201, resp.text

        # logout also requires CSRF, then invalidates the session
        resp = await client.post("/api/auth/logout")
        assert resp.status_code == 403, resp.text
        resp = await client.post("/api/auth/logout", headers={"X-CSRF-Token": csrf})
        assert resp.status_code == 200, resp.text

        resp = await client.get("/api/auth/me")
        assert resp.status_code == 401, resp.text

    # a non-admin user gets 403 on admin routes entirely (even read-only ones)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/api/auth/login", json={"email": "member@test.local", "password": "hunter2222"})
        assert resp.status_code == 200, resp.text
        resp = await client.get("/api/admin/users")
        assert resp.status_code == 403, resp.text

    os.remove(TMP_DB)
    print("All auth tests passed.")


asyncio.run(main())
