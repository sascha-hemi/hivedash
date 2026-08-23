"""Exercises app/db/repository.py against a temp-file SQLite DB - no FastAPI involved.

Covers: natural-key upserts (re-polling the same host/guest updates in place, doesn't duplicate),
pruning of entries that disappeared from a successful poll, and the default-dashboard
auto-population that keeps every known service attached to it.
"""
import asyncio
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

TMP_DB = tempfile.NamedTemporaryFile(suffix=".db", delete=False).name
os.environ["DATABASE_PATH"] = TMP_DB
# Keep this test offline/deterministic - the dashboard-icons catalog fallback is exercised
# manually (see CLAUDE.md), not here, same as the OIDC handshake.
os.environ["LOGO_CATALOG_AUTO_IMPORT"] = "false"

from app.clients.npm import ProxyHost as ProxyHostDC  # noqa: E402
from app.clients.proxmox import Guest  # noqa: E402
from app.db import admin_repository, repository  # noqa: E402
from app.db.engine import get_sessionmaker, init_models  # noqa: E402
from app.db.models import Category, DashboardItem, Logo  # noqa: E402
from app.db.models import ProxyHost as ProxyHostRow  # noqa: E402
from sqlalchemy import select  # noqa: E402


def host(id, forward_host="10.0.0.5", online=True, domain_names=None):
    return ProxyHostDC(
        id=id, domain_names=domain_names or [f"svc{id}.example.com"], forward_scheme="http",
        forward_host=forward_host, forward_port=80, enabled=True, online=online, ssl=False,
    )


def guest(vmid, node="pve", status="running"):
    return Guest(
        vmid=vmid, name=f"guest-{vmid}", node=node, kind="lxc", status=status,
        cpu=0.1, mem=100, maxmem=200, ip_addresses=["10.0.0.9"],
    )


def test_domain_match_candidates_uses_leftmost_label_only():
    # a real false-positive hit during development: matching the full FQDN let an unrelated
    # fragment of the base domain ("provider.example" containing "ide") cause a wrong auto-match.
    assert repository._domain_match_candidates(["auth.provider.example"]) == ["auth"]
    assert repository._domain_match_candidates(["plex.example.com", "media.example.com"]) == [
        "plex", "media",
    ]


async def main():
    await init_models()
    sessionmaker = get_sessionmaker()

    # 1. first poll: two hosts, one guest
    async with sessionmaker() as session:
        await repository.upsert_proxy_hosts(session, [host(1), host(2)])
        await repository.upsert_guests(session, [guest(100)])
        await repository.ensure_default_dashboard_items(session)

    async with sessionmaker() as session:
        loaded_hosts = await repository.load_proxy_hosts(session)
        loaded_guests = await repository.load_guests(session)
        assert {h.id for h in loaded_hosts} == {1, 2}
        assert {g.vmid for g in loaded_guests} == {100}

        dash = await repository.ensure_default_dashboard(session)
        items = (
            await session.execute(select(DashboardItem).where(DashboardItem.dashboard_id == dash.id))
        ).scalars().all()
        assert len(items) == 3, "default dashboard should auto-attach all 2 hosts + 1 guest"

    # 2. re-poll with host 1 updated (now offline) and host 2 gone -> upsert in place + prune
    async with sessionmaker() as session:
        await repository.upsert_proxy_hosts(session, [host(1, online=False)])
        await repository.ensure_default_dashboard_items(session)

    async with sessionmaker() as session:
        loaded_hosts = await repository.load_proxy_hosts(session)
        assert {h.id for h in loaded_hosts} == {1}, "host 2 should have been pruned"
        assert loaded_hosts[0].online is False, "host 1 should be updated in place, not duplicated"

    # 3. a failed poll (guests=None from the caller's perspective) must NOT touch existing guests -
    # this is the "last known good stays visible" behavior confirmed with the user
    async with sessionmaker() as session:
        # simulate main.py's poll_once(): guests is None on failure, so upsert_guests is simply
        # never called - nothing to assert here beyond "the row from step 1 is still there"
        loaded_guests = await repository.load_guests(session)
        assert {g.vmid for g in loaded_guests} == {100}

    # 4. resolved items expose the natural key, not internal DB ids
    async with sessionmaker() as session:
        dash = await repository.ensure_default_dashboard(session)
        resolved = await repository.load_resolved_dashboard_items(session, dash.id)
        host_keys = {r.key for r in resolved if r.kind == "proxy_host"}
        guest_keys = {r.key for r in resolved if r.kind == "guest"}
        assert host_keys == {1}
        assert guest_keys == {("pve", 100)}

    # 5. logo auto-assignment is "sticky but self-healing" - poll with no matching logo present,
    # add a matching logo, poll again (self-healing), manually override, then poll a third time
    # with an even-better-matching logo present (must NOT change - sticky).
    host3 = host(3, forward_host="10.0.0.7", domain_names=["plexy.example.com"])

    async with sessionmaker() as session:
        await repository.upsert_proxy_hosts(session, [host3])
    async with sessionmaker() as session:
        row = (
            await session.execute(select(ProxyHostRow).where(ProxyHostRow.npm_host_id == 3))
        ).scalar_one()
        assert row.logo_id is None, "no logo uploaded yet -> no match"

    async with sessionmaker() as session:
        logo = Logo(name="Plex", keywords=["plex"], content_type="image/svg+xml", data=b"<svg/>")
        session.add(logo)
        await session.commit()
        await session.refresh(logo)
        plex_logo_id = logo.id

    async with sessionmaker() as session:
        await repository.upsert_proxy_hosts(session, [host3])  # re-poll now that a logo exists
    async with sessionmaker() as session:
        row = (
            await session.execute(select(ProxyHostRow).where(ProxyHostRow.npm_host_id == 3))
        ).scalar_one()
        assert row.logo_id == plex_logo_id, "self-healing: a logo uploaded after discovery should still get picked up"

    async with sessionmaker() as session:
        custom_logo = Logo(name="Custom", keywords=["totally-unrelated"], content_type="image/png", data=b"\x89PNG")
        session.add(custom_logo)
        await session.commit()
        await session.refresh(custom_logo)
        custom_logo_id = custom_logo.id
        row = (
            await session.execute(select(ProxyHostRow).where(ProxyHostRow.npm_host_id == 3))
        ).scalar_one()
        row.logo_id = custom_logo_id  # simulate a manual admin override
        await session.commit()

    async with sessionmaker() as session:
        session.add(Logo(name="Plex Better", keywords=["plexy"], content_type="image/svg+xml", data=b"<svg/>"))
        await session.commit()
        await repository.upsert_proxy_hosts(session, [host3])  # even-better match now exists
    async with sessionmaker() as session:
        row = (
            await session.execute(select(ProxyHostRow).where(ProxyHostRow.npm_host_id == 3))
        ).scalar_one()
        assert row.logo_id == custom_logo_id, "manual override must be sticky, not overwritten by a later poll"

    # 5b. explicitly clearing a logo to "kein Logo" (via admin_repository.set_service_details, the
    # real code path the "Dienste" page uses) must survive a later poll even though a matching
    # logo exists - this is the bug logo_locked fixes: logo_id IS NULL used to be indistinguishable
    # between "never evaluated yet" and "admin deliberately removed it", so the self-healing
    # COALESCE would silently reassign the very logo the admin just cleared.
    # host3 is kept in every upsert call alongside host4 here - passing only [host4] would prune
    # host3 and, via SQLite's rowid reuse, disturb the dangling DashboardItem step 6 below relies
    # on (a pre-existing, unrelated fragility - not something to make worse here).
    host4 = host(4, forward_host="10.0.0.8", domain_names=["plexy2.example.com"])
    async with sessionmaker() as session:
        await repository.upsert_proxy_hosts(session, [host3, host4])  # auto-matches an existing logo
    async with sessionmaker() as session:
        row = (
            await session.execute(select(ProxyHostRow).where(ProxyHostRow.npm_host_id == 4))
        ).scalar_one()
        assert row.logo_id is not None, "should auto-match a logo already in the library"
        assert row.logo_locked is False
        host4_id = row.id

    async with sessionmaker() as session:
        await admin_repository.set_service_details(session, "proxy_host", host4_id, logo_id=None)

    async with sessionmaker() as session:
        await repository.upsert_proxy_hosts(session, [host3, host4])  # re-poll - must NOT reassign
    async with sessionmaker() as session:
        row = (
            await session.execute(select(ProxyHostRow).where(ProxyHostRow.npm_host_id == 4))
        ).scalar_one()
        assert row.logo_id is None, "explicitly-cleared logo must survive a later poll"
        assert row.logo_locked is True

    # 6. load_categories() returns a dashboard's own categories, ordered, and
    # load_resolved_dashboard_items() exposes item_id/category_id off the already-loaded row.
    async with sessionmaker() as session:
        dash = await repository.ensure_default_dashboard(session)
        session.add(Category(dashboard_id=dash.id, name="Second", sort_order=1))
        session.add(Category(dashboard_id=dash.id, name="First", sort_order=0))
        await session.commit()

    async with sessionmaker() as session:
        dash = await repository.ensure_default_dashboard(session)
        categories = await repository.load_categories(session, dash.id)
        assert [c["name"] for c in categories] == ["First", "Second"], "must be ordered by sort_order"

        cat_id = categories[0]["id"]
        # inner join to ProxyHostRow, not just "any item with a non-null proxy_host_id" - a
        # dangling DashboardItem from a since-pruned host can still exist (SQLite never enforces
        # ondelete=CASCADE here), and would otherwise be picked ambiguously by plain .first().
        row = (
            await session.execute(
                select(DashboardItem).join(ProxyHostRow, DashboardItem.proxy_host_id == ProxyHostRow.id)
            )
        ).scalars().first()
        row.category_id = cat_id
        await session.commit()

    async with sessionmaker() as session:
        dash = await repository.ensure_default_dashboard(session)
        resolved = await repository.load_resolved_dashboard_items(session, dash.id)
        categorized = [r for r in resolved if r.category_id == cat_id]
        assert len(categorized) == 1
        assert categorized[0].item_id == row.id

    os.remove(TMP_DB)
    print("All db_repository tests passed.")


test_domain_match_candidates_uses_leftmost_label_only()
asyncio.run(main())
