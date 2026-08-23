"""Drives the real FastAPI app over an in-process ASGI transport against a temp-file SQLite DB:
category CRUD, tile_size, category_id round-tripping through the bulk items PATCH (including
cross-dashboard rejection), and the delete-category null-out behavior."""
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

from app.db import admin_repository, repository  # noqa: E402
from app.db.engine import get_sessionmaker, init_models  # noqa: E402
from app.db.models import Dashboard, ProxyHost  # noqa: E402
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
        default_dash = await repository.ensure_default_dashboard(session)
        default_dash_id = default_dash.id

        session.add(
            ProxyHost(
                npm_host_id=1, domain_names=["svc.example.com"], forward_scheme="http",
                forward_host="10.0.0.5", forward_port=80, enabled=True, online=True, ssl=False,
            )
        )
        await session.commit()

    async with sessionmaker() as session:
        host = (await session.execute(select(ProxyHost).where(ProxyHost.npm_host_id == 1))).scalar_one()
        item = await repository.attach_item_to_dashboard(session, default_dash_id, proxy_host_id=host.id)
        item_id = item.id

    transport = httpx.ASGITransport(app=app)

    # non-admin gets 403 on category routes
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        await client.post("/api/auth/login", json={"email": "member@test.local", "password": "hunter2222"})
        resp = await client.get(f"/api/admin/dashboards/{default_dash_id}/categories")
        assert resp.status_code == 403, resp.text

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/api/auth/login", json={"email": "admin@test.local", "password": "correct-horse"})
        assert resp.status_code == 200, resp.text
        csrf = client.cookies["csrf_token"]

        # tile_size PATCH
        resp = await client.patch(
            f"/api/admin/dashboards/{default_dash_id}", json={"tile_size": "large"},
            headers={"X-CSRF-Token": csrf},
        )
        assert resp.status_code == 200 and resp.json()["tile_size"] == "large", resp.text

        # rejects an invalid tile_size value
        resp = await client.patch(
            f"/api/admin/dashboards/{default_dash_id}", json={"tile_size": "huge"},
            headers={"X-CSRF-Token": csrf},
        )
        assert resp.status_code == 422, resp.text

        # category CRUD
        resp = await client.post(
            f"/api/admin/dashboards/{default_dash_id}/categories", json={"name": "Media"},
            headers={"X-CSRF-Token": csrf},
        )
        assert resp.status_code == 201, resp.text
        category = resp.json()
        assert category["name"] == "Media" and category["sort_order"] == 0, category
        category_id = category["id"]

        resp = await client.post(
            f"/api/admin/dashboards/{default_dash_id}/categories", json={"name": "Tools"},
            headers={"X-CSRF-Token": csrf},
        )
        second_category = resp.json()
        assert second_category["sort_order"] == 1, "should default to appended-at-end order"

        resp = await client.get(f"/api/admin/dashboards/{default_dash_id}/categories")
        assert [c["name"] for c in resp.json()] == ["Media", "Tools"], resp.json()

        resp = await client.patch(
            f"/api/admin/dashboards/{default_dash_id}/categories/{category_id}",
            json={"name": "Media & Streaming"}, headers={"X-CSRF-Token": csrf},
        )
        assert resp.status_code == 200 and resp.json()["name"] == "Media & Streaming", resp.text

        # category_id round-trips through the bulk items PATCH
        resp = await client.patch(
            f"/api/admin/dashboards/{default_dash_id}/items",
            json=[{"item_id": item_id, "category_id": category_id}],
            headers={"X-CSRF-Token": csrf},
        )
        assert resp.status_code == 200, resp.text
        updated_item = next(i for i in resp.json() if i["item_id"] == item_id)
        assert updated_item["category_id"] == category_id, updated_item

        # a category from a DIFFERENT dashboard must be rejected, not silently accepted
        other_dash = await _create_other_dashboard_with_category(sessionmaker, default_dash_id)
        resp = await client.patch(
            f"/api/admin/dashboards/{default_dash_id}/items",
            json=[{"item_id": item_id, "category_id": other_dash["category_id"]}],
            headers={"X-CSRF-Token": csrf},
        )
        assert resp.status_code == 404, resp.text

        # deleting a category nulls out referencing items rather than leaving them dangling
        resp = await client.delete(
            f"/api/admin/dashboards/{default_dash_id}/categories/{category_id}",
            headers={"X-CSRF-Token": csrf},
        )
        assert resp.status_code == 200, resp.text

        resp = await client.get(f"/api/admin/dashboards/{default_dash_id}/items")
        item_after_delete = next(i for i in resp.json() if i["item_id"] == item_id)
        assert item_after_delete["category_id"] is None, item_after_delete

    os.remove(TMP_DB)
    print("All admin_dashboards tests passed.")


async def _create_other_dashboard_with_category(sessionmaker, clone_from_id: int) -> dict:
    async with sessionmaker() as session:
        source = await session.get(Dashboard, clone_from_id)
        dash = await admin_repository.create_dashboard(session, name="Other", clone_from=source)
        category = await admin_repository.create_category(session, dash.id, name="Elsewhere")
        return {"dashboard_id": dash.id, "category_id": category.id}


asyncio.run(main())
