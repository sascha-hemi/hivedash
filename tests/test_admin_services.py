"""Drives the real FastAPI app over an in-process ASGI transport against a temp-file SQLite DB:
the "Dienste" admin page's backing endpoints - global logo/name/url on an auto-discovered
proxy_host/guest (PATCH /api/admin/services/{kind}/{id}), and full CRUD for admin-created custom
services that have no NPM/Proxmox counterpart at all."""
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
from app.db.models import Guest, ProxyHost  # noqa: E402
from app.main import app  # noqa: E402


async def main():
    await init_models()
    sessionmaker = get_sessionmaker()

    async with sessionmaker() as session:
        await admin_repository.create_user(
            session, email="admin@test.local", password="correct-horse",
            display_name="Admin", role="admin", dashboard_id=None,
        )
        default_dash = await repository.ensure_default_dashboard(session)
        default_dash_id = default_dash.id

        session.add(
            ProxyHost(
                npm_host_id=1, domain_names=["svc.example.com"], forward_scheme="http",
                forward_host="10.0.0.5", forward_port=80, enabled=True, online=True, ssl=False,
            )
        )
        session.add(
            Guest(
                node="pve", vmid=100, kind="lxc", name="homeassistant", status="running",
                cpu=0.1, mem=1024, maxmem=2048, ip_addresses=[],
            )
        )
        # a second, MATCHED pair (guest's IP == host's forward_host) - used to verify the
        # "Dienste" list folds a matched pair into one row instead of listing it twice.
        session.add(
            ProxyHost(
                npm_host_id=2, domain_names=["matched.example.com"], forward_scheme="http",
                forward_host="10.0.0.9", forward_port=80, enabled=True, online=True, ssl=False,
            )
        )
        session.add(
            Guest(
                node="pve", vmid=200, kind="lxc", name="matched-guest", status="running",
                cpu=0.2, mem=2048, maxmem=4096, ip_addresses=["10.0.0.9"],
            )
        )
        await session.commit()

    async with sessionmaker() as session:
        host = (await session.execute(select(ProxyHost).where(ProxyHost.npm_host_id == 1))).scalar_one()
        guest = (await session.execute(select(Guest).where(Guest.vmid == 100))).scalar_one()
        matched_host = (await session.execute(select(ProxyHost).where(ProxyHost.npm_host_id == 2))).scalar_one()
        matched_guest = (await session.execute(select(Guest).where(Guest.vmid == 200))).scalar_one()
        await repository.attach_item_to_dashboard(session, default_dash_id, proxy_host_id=host.id)
        await repository.attach_item_to_dashboard(session, default_dash_id, guest_id=guest.id)
        await repository.attach_item_to_dashboard(session, default_dash_id, proxy_host_id=matched_host.id)
        await repository.attach_item_to_dashboard(session, default_dash_id, guest_id=matched_guest.id)
        host_id, guest_id = host.id, guest.id
        matched_guest_id = matched_guest.id

    transport = httpx.ASGITransport(app=app)

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/api/auth/login", json={"email": "admin@test.local", "password": "correct-horse"})
        assert resp.status_code == 200, resp.text
        csrf = client.cookies["csrf_token"]

        # --- global identity on an auto-discovered guest (no NPM proxy host at all, like
        # HomeAssistant) - name/url are global, not per-dashboard.
        resp = await client.patch(
            f"/api/admin/services/guest/{guest_id}",
            json={"custom_name": "Home Assistant", "custom_url": "http://homeassistant.local:8123"},
            headers={"X-CSRF-Token": csrf},
        )
        assert resp.status_code == 200, resp.text

        resp = await client.get("/api/dashboard")
        infra = next(s for s in resp.json()["sections"] if s["name"] == "Infrastruktur")
        tile = next(t for t in infra["tiles"] if t["vmid"] == 100)
        assert tile["name"] == "Home Assistant", tile
        assert tile["href"] == "http://homeassistant.local:8123", tile

        # a partial update (name only) must not clobber the url already set (exclude_unset).
        resp = await client.patch(
            f"/api/admin/services/guest/{guest_id}", json={"custom_name": "HA"},
            headers={"X-CSRF-Token": csrf},
        )
        assert resp.status_code == 200, resp.text
        resp = await client.get(f"/api/admin/dashboards/{default_dash_id}/items")
        item = next(i for i in resp.json() if i["kind"] == "guest" and i["service_id"] == guest_id)
        assert item["label"] == "HA", item

        # the "Dienste" page's discovered-services listing shows every known service regardless
        # of dashboard attachment, with the current identity override applied.
        resp = await client.get("/api/admin/services/discovered")
        discovered = resp.json()
        guest_row = next(s for s in discovered if s["kind"] == "guest" and s["id"] == guest_id)
        assert guest_row["custom_name"] == "HA", guest_row
        assert guest_row["custom_url"] == "http://homeassistant.local:8123", guest_row

        # a matched proxy_host+guest pair (see app.merge's IP-matching) folds into a single row,
        # not two - it must never appear as its own separate "guest" row...
        assert not any(
            s["kind"] == "guest" and s["id"] == matched_guest_id for s in discovered
        ), discovered
        # ...and the one row that does represent it is the proxy_host side (editing still targets
        # the host's own custom_name/custom_url/logo_id), but its displayed label prefers the
        # guest's own name over the NPM subdomain - the same default the live tile itself uses -
        # with the subdomain demoted to secondary_label for context.
        matched_row = next(s for s in discovered if s["kind"] == "proxy_host" and s["label"] == "matched-guest")
        assert matched_row["secondary_label"] == "matched.example.com", matched_row

        # an unmatched proxy_host/guest has no secondary_label at all - its own label IS the
        # NPM-derived name, there's nothing else to show.
        unmatched_host_row = next(s for s in discovered if s["kind"] == "proxy_host" and s["id"] == host_id)
        assert unmatched_host_row["secondary_label"] is None, unmatched_host_row
        assert unmatched_host_row["label"] == "svc.example.com", unmatched_host_row

        # the same folding applies to the "Dashboards" curation table (Reihenfolge & Sichtbarkeit):
        # a matched guest's own DashboardItem is excluded there too - while matched it's controlled
        # solely by the proxy host's item and toggling it would have zero visible effect, so
        # showing it would just be a confusing dead control. The unmatched guest (homeassistant)
        # still gets its own row as normal.
        resp = await client.get(f"/api/admin/dashboards/{default_dash_id}/items")
        dashboard_items = resp.json()
        assert not any(
            i["kind"] == "guest" and i["service_id"] == matched_guest_id for i in dashboard_items
        ), dashboard_items
        assert any(
            i["kind"] == "proxy_host" and i["service_id"] == matched_host.id for i in dashboard_items
        ), dashboard_items
        assert any(
            i["kind"] == "guest" and i["service_id"] == guest_id for i in dashboard_items
        ), "the unmatched guest must still have its own row"

        # unknown proxy_host/guest id -> 404, not a silent no-op
        resp = await client.patch(
            f"/api/admin/services/proxy_host/999999", json={"custom_name": "x"},
            headers={"X-CSRF-Token": csrf},
        )
        assert resp.status_code == 404, resp.text

        # --- custom services (no NPM/Proxmox counterpart at all) ---
        resp = await client.post(
            "/api/admin/custom-services",
            json={"name": "Fritzbox", "url": "http://192.168.1.1"},
            headers={"X-CSRF-Token": csrf},
        )
        assert resp.status_code == 201, resp.text
        custom = resp.json()
        assert custom["name"] == "Fritzbox" and custom["url"] == "http://192.168.1.1", custom
        custom_id = custom["id"]

        # a freshly-created custom service appears on the default dashboard immediately, without
        # waiting for the next poll cycle.
        resp = await client.get(f"/api/admin/dashboards/{default_dash_id}/items")
        items = resp.json()
        custom_item = next(i for i in items if i["kind"] == "custom_service" and i["service_id"] == custom_id)
        assert custom_item["label"] == "Fritzbox", custom_item

        resp = await client.get("/api/dashboard")
        services = next(s for s in resp.json()["sections"] if s["name"] == "Dienste")
        custom_tile = next(t for t in services["tiles"] if t["type"] == "custom")
        assert custom_tile["name"] == "Fritzbox", custom_tile
        assert custom_tile["href"] == "http://192.168.1.1", custom_tile

        # appears in the "available services" union too (for attaching to other dashboards)
        resp = await client.get("/api/admin/services")
        assert any(s["kind"] == "custom_service" and s["id"] == custom_id for s in resp.json())

        # rename/re-url via PATCH
        resp = await client.patch(
            f"/api/admin/custom-services/{custom_id}", json={"url": "http://fritz.box"},
            headers={"X-CSRF-Token": csrf},
        )
        assert resp.status_code == 200 and resp.json()["url"] == "http://fritz.box", resp.text
        assert resp.json()["name"] == "Fritzbox", "unset fields must be left untouched"

        # deleting it removes both the service and its dashboard item (not left dangling - a
        # DashboardItem must reference exactly one target per the model's check constraint).
        resp = await client.delete(
            f"/api/admin/custom-services/{custom_id}", headers={"X-CSRF-Token": csrf}
        )
        assert resp.status_code == 200, resp.text
        resp = await client.get(f"/api/admin/dashboards/{default_dash_id}/items")
        assert all(i["kind"] != "custom_service" for i in resp.json())

        resp = await client.get("/api/admin/custom-services")
        assert all(s["id"] != custom_id for s in resp.json())

    os.remove(TMP_DB)
    print("All admin_services tests passed.")


asyncio.run(main())
