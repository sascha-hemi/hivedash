"""Drives the real FastAPI app (no mocking) over an in-process ASGI transport against a temp-file
SQLite DB: login/logout, session cookie + CSRF double-submit, and role-gated admin routes."""
import asyncio
import os
import sys
import tempfile
from datetime import timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

TMP_DB = tempfile.NamedTemporaryFile(suffix=".db", delete=False).name
os.environ["DATABASE_PATH"] = TMP_DB
os.environ.setdefault("COOKIE_SECURE", "false")

import httpx  # noqa: E402
from sqlalchemy import select  # noqa: E402

from app.auth.security import (  # noqa: E402
    generate_csrf_token,
    generate_session_token,
    hash_session_token,
)
from app.db import admin_repository  # noqa: E402
from app.db.engine import get_sessionmaker, init_models  # noqa: E402
from app.db.models import Session as SessionModel  # noqa: E402
from app.db.models import User  # noqa: E402
from app.db.timeutil import utcnow  # noqa: E402
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
        await admin_repository.create_user(
            session, email="sso@test.local", password=None,
            display_name="SSO User", role="user", dashboard_id=None,
        )

    transport = httpx.ASGITransport(app=app)

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/api/auth/login", json={"email": "admin@test.local", "password": "wrong"})
        assert resp.status_code == 401, resp.text

        resp = await client.post("/api/auth/login", json={"email": "admin@test.local", "password": "correct-horse"})
        assert resp.status_code == 200, resp.text
        assert "session" in resp.cookies and "csrf_token" in resp.cookies
        csrf = client.cookies["csrf_token"]

        resp = await client.get("/api/auth/me")
        assert resp.status_code == 200, resp.text
        assert resp.json() == {
            "id": resp.json()["id"], "email": "admin@test.local",
            "display_name": "Admin", "role": "admin", "locale": None, "has_password": True,
            "search_engine": None,
        }

        # self-service locale: no CSRF -> 403, same rule as every other mutating route
        resp = await client.patch("/api/auth/me", json={"locale": "de"})
        assert resp.status_code == 403, resp.text

        resp = await client.patch("/api/auth/me", json={"locale": "de"}, headers={"X-CSRF-Token": csrf})
        assert resp.status_code == 200 and resp.json()["locale"] == "de", resp.text

        # rejects a locale the frontend doesn't actually ship a translation for
        resp = await client.patch("/api/auth/me", json={"locale": "xx"}, headers={"X-CSRF-Token": csrf})
        assert resp.status_code == 422, resp.text

        # null resets to auto-detect - must actually be applied (exclude_unset, not "is None")
        resp = await client.patch("/api/auth/me", json={"locale": None}, headers={"X-CSRF-Token": csrf})
        assert resp.status_code == 200 and resp.json()["locale"] is None, resp.text

        # self-service search engine: same shape as locale
        resp = await client.patch("/api/auth/me", json={"search_engine": "bing"}, headers={"X-CSRF-Token": csrf})
        assert resp.status_code == 200 and resp.json()["search_engine"] == "bing", resp.text

        resp = await client.patch("/api/auth/me", json={"search_engine": "altavista"}, headers={"X-CSRF-Token": csrf})
        assert resp.status_code == 422, resp.text

        resp = await client.patch("/api/auth/me", json={"search_engine": None}, headers={"X-CSRF-Token": csrf})
        assert resp.status_code == 200 and resp.json()["search_engine"] is None, resp.text

        # public config: engine catalog + instance default (SEARCH_ENGINE env, defaults to google)
        resp = await client.get("/api/auth/config")
        assert resp.status_code == 200, resp.text
        assert resp.json()["default_search_engine"] == "google"
        assert "bing" in resp.json()["search_engines"] and "google" in resp.json()["search_engines"]

        # self-service password change: wrong current password -> 401, nothing changed
        resp = await client.patch(
            "/api/auth/me",
            json={"current_password": "not-it", "new_password": "new-horse-battery"},
            headers={"X-CSRF-Token": csrf},
        )
        assert resp.status_code == 401, resp.text

        # empty new password -> 422
        resp = await client.patch(
            "/api/auth/me",
            json={"current_password": "correct-horse", "new_password": ""},
            headers={"X-CSRF-Token": csrf},
        )
        assert resp.status_code == 422, resp.text

        # correct current password -> changed, and the old password no longer works
        resp = await client.patch(
            "/api/auth/me",
            json={"current_password": "correct-horse", "new_password": "new-horse-battery"},
            headers={"X-CSRF-Token": csrf},
        )
        assert resp.status_code == 200, resp.text
        resp = await client.post("/api/auth/login", json={"email": "admin@test.local", "password": "correct-horse"})
        assert resp.status_code == 401, resp.text
        resp = await client.post("/api/auth/login", json={"email": "admin@test.local", "password": "new-horse-battery"})
        assert resp.status_code == 200, resp.text
        csrf = client.cookies["csrf_token"]

        # read-only admin route needs no CSRF header
        resp = await client.get("/api/admin/users")
        assert resp.status_code == 200, resp.text
        assert {u["email"] for u in resp.json()} == {
            "admin@test.local", "member@test.local", "sso@test.local",
        }

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

    # an OIDC-provisioned account (no local password) can never set one via self-service, even
    # with a valid session - simulate that session directly since there's no password to log in
    # with (mirrors what provision_user_from_oidc_claims + _start_session would produce)
    async with sessionmaker() as session:
        sso_user = (await session.execute(select(User).where(User.email == "sso@test.local"))).scalar_one()
        sso_token = generate_session_token()
        sso_csrf = generate_csrf_token()
        session.add(SessionModel(
            token_hash=hash_session_token(sso_token), csrf_token=sso_csrf, user_id=sso_user.id,
            expires_at=utcnow() + timedelta(days=1),
        ))
        await session.commit()

    async with httpx.AsyncClient(
        transport=transport, base_url="http://test",
        cookies={"session": sso_token, "csrf_token": sso_csrf},
    ) as client:
        resp = await client.get("/api/auth/me")
        assert resp.status_code == 200 and resp.json()["has_password"] is False, resp.text

        resp = await client.patch(
            "/api/auth/me",
            json={"current_password": "whatever", "new_password": "whatever2"},
            headers={"X-CSRF-Token": sso_csrf},
        )
        assert resp.status_code == 400, resp.text

    os.remove(TMP_DB)
    print("All auth tests passed.")


asyncio.run(main())
