"""DB <-> dataclass bridging and dashboard-curation queries.

Keeps app.merge.build_dashboard() completely DB-agnostic: load_proxy_hosts()/load_guests() hand
back the exact ProxyHost/Guest dataclasses it already expects, and upsert_proxy_hosts()/
upsert_guests() are the only place that knows how to turn a fresh poll result into rows.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Literal

import httpx
from sqlalchemy import delete, func, select, tuple_
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.clients import dashboard_icons
from app.clients.npm import ProxyHost as ProxyHostDC
from app.clients.proxmox import Guest as GuestDC
from app.config import settings
from app.db.models import Category, CustomService, Dashboard, DashboardItem, Guest, Logo, ProxyHost
from app.db.timeutil import utcnow as _utcnow
from app.logo_matching import LogoCandidate, match_logo

logger = logging.getLogger("dashboard.logos")


async def _load_logo_candidates(session: AsyncSession) -> list[LogoCandidate]:
    rows = (await session.execute(select(Logo.id, Logo.keywords))).all()
    return [LogoCandidate(id=row.id, keywords=row.keywords) for row in rows]


def _domain_match_candidates(domain_names: list[str]) -> list[str]:
    """Match only against a domain's leftmost label (e.g. "plex" from "plex.example.com"), not
    the full FQDN - otherwise an unrelated fragment of the base domain can coincidentally contain
    a keyword (a real case hit during development: "provider.example" contains "ide", matching a
    "code"/VS Code alias)."""
    return [d.split(".")[0] for d in domain_names if d]


async def _match_or_fetch_logo(
    session: AsyncSession, candidates: list[str], logos: list[LogoCandidate]
) -> int | None:
    """Local Logo library first (respects admin curation/overrides); only falls back to the
    dashboard-icons catalog for a service that still has no match. Best-effort: a catalog miss or
    a network failure here never breaks the poll, it just leaves logo_id unset for another
    self-healing attempt next cycle (see the COALESCE comment in upsert_proxy_hosts())."""
    matched = match_logo(candidates, logos)
    if matched is not None:
        return matched

    if not settings.logo_catalog_auto_import:
        return None

    try:
        slug = await dashboard_icons.find_best_slug(candidates)
        if slug is None:
            return None

        existing_id = (
            await session.execute(select(Logo.id).where(Logo.name == slug))
        ).scalar_one_or_none()
        if existing_id is not None:
            logos.append(LogoCandidate(id=existing_id, keywords=[slug]))
            return existing_id

        data, content_type, aliases = await dashboard_icons.fetch_icon(slug)
    except (httpx.HTTPError, ValueError) as exc:
        logger.debug("dashboard-icons lookup failed for %s: %s", candidates, exc)
        return None

    keywords = sorted({slug.lower(), *(a.lower() for a in aliases)})
    logo = Logo(name=slug, keywords=keywords, content_type=content_type, data=data)
    session.add(logo)
    await session.flush()
    logos.append(LogoCandidate(id=logo.id, keywords=keywords))
    logger.info("Auto-imported logo %r from dashboard-icons for %s", slug, candidates)
    return logo.id


# --- poll result persistence -------------------------------------------------------------


async def upsert_proxy_hosts(session: AsyncSession, hosts: list[ProxyHostDC]) -> None:
    """Upsert this poll's hosts by npm_host_id, then prune rows no longer present.

    Only call this when the NPM poll succeeded. On a failed poll, simply don't call it -
    existing rows (and thus the dashboard) are left untouched.
    """
    now = _utcnow()
    logos = await _load_logo_candidates(session)
    locked_by_npm_id = dict(
        (await session.execute(select(ProxyHost.npm_host_id, ProxyHost.logo_locked))).all()
    )
    for h in hosts:
        values = dict(
            npm_host_id=h.id,
            domain_names=h.domain_names,
            forward_scheme=h.forward_scheme,
            forward_host=h.forward_host,
            forward_port=h.forward_port,
            enabled=h.enabled,
            online=h.online,
            ssl=h.ssl,
        )
        # once the admin has explicitly touched logo_id (to a specific logo, or deliberately to
        # "kein Logo") it's locked - skip auto-matching entirely rather than risk silently
        # re-assigning a logo the admin just removed (see Guest/ProxyHost.logo_locked docstring).
        if locked_by_npm_id.get(h.id, False):
            matched_logo_id = None
        else:
            matched_logo_id = await _match_or_fetch_logo(
                session, _domain_match_candidates(h.domain_names), logos
            )
        stmt = sqlite_insert(ProxyHost).values(
            **values, logo_id=matched_logo_id, first_seen_at=now, last_seen_at=now
        )
        # logo_id is "sticky but self-healing" while unlocked: a manual assignment or a previous
        # auto-match is never overwritten (COALESCE keeps the existing value when non-null), but a
        # still-NULL logo_id gets re-evaluated every poll, so a logo uploaded after discovery still
        # gets picked up - unlike first_seen_at (frozen forever by simply never appearing in set_
        # at all), this column must stay writable while null, hence the COALESCE instead of
        # omission. Once locked, matched_logo_id is always None here, so COALESCE just preserves
        # whatever's already there (including a deliberately-NULL "kein Logo").
        stmt = stmt.on_conflict_do_update(
            index_elements=[ProxyHost.npm_host_id],
            set_={
                **values,
                "last_seen_at": now,
                "logo_id": func.coalesce(ProxyHost.logo_id, stmt.excluded.logo_id),
            },
        )
        await session.execute(stmt)

    seen_ids = [h.id for h in hosts]
    if seen_ids:
        await session.execute(delete(ProxyHost).where(ProxyHost.npm_host_id.not_in(seen_ids)))
    else:
        await session.execute(delete(ProxyHost))
    await session.commit()


async def upsert_guests(session: AsyncSession, guests: list[GuestDC]) -> None:
    """Upsert this poll's guests by (node, vmid), then prune rows no longer present.

    Only call this when the Proxmox poll succeeded - see upsert_proxy_hosts() docstring.
    """
    now = _utcnow()
    logos = await _load_logo_candidates(session)
    locked_by_key = {
        (row["node"], row["vmid"]): row["logo_locked"]
        for row in (await session.execute(select(Guest.node, Guest.vmid, Guest.logo_locked))).mappings()
    }
    for g in guests:
        values = dict(
            node=g.node,
            vmid=g.vmid,
            kind=g.kind,
            name=g.name,
            status=g.status,
            cpu=g.cpu,
            mem=g.mem,
            maxmem=g.maxmem,
            ip_addresses=g.ip_addresses,
        )
        if locked_by_key.get((g.node, g.vmid), False):
            matched_logo_id = None
        else:
            matched_logo_id = await _match_or_fetch_logo(session, [g.name], logos)
        stmt = sqlite_insert(Guest).values(
            **values, logo_id=matched_logo_id, first_seen_at=now, last_seen_at=now
        )
        # see the matching comment in upsert_proxy_hosts() - same "sticky but self-healing while
        # unlocked" rule.
        stmt = stmt.on_conflict_do_update(
            index_elements=[Guest.node, Guest.vmid],
            set_={
                **values,
                "last_seen_at": now,
                "logo_id": func.coalesce(Guest.logo_id, stmt.excluded.logo_id),
            },
        )
        await session.execute(stmt)

    seen_keys = [(g.node, g.vmid) for g in guests]
    if seen_keys:
        await session.execute(
            delete(Guest).where(tuple_(Guest.node, Guest.vmid).not_in(seen_keys))
        )
    else:
        await session.execute(delete(Guest))
    await session.commit()


async def load_proxy_hosts(session: AsyncSession) -> list[ProxyHostDC]:
    rows = (await session.execute(select(ProxyHost))).scalars().all()
    return [
        ProxyHostDC(
            id=r.npm_host_id,
            domain_names=r.domain_names,
            forward_scheme=r.forward_scheme,
            forward_host=r.forward_host,
            forward_port=r.forward_port,
            enabled=r.enabled,
            online=r.online,
            ssl=r.ssl,
        )
        for r in rows
    ]


async def load_guests(session: AsyncSession) -> list[GuestDC]:
    rows = (await session.execute(select(Guest))).scalars().all()
    return [
        GuestDC(
            vmid=r.vmid,
            name=r.name,
            node=r.node,
            kind=r.kind,
            status=r.status,
            cpu=r.cpu,
            mem=r.mem,
            maxmem=r.maxmem,
            ip_addresses=r.ip_addresses,
        )
        for r in rows
    ]


# --- dashboards ---------------------------------------------------------------------------


async def ensure_default_dashboard(session: AsyncSession) -> Dashboard:
    result = await session.execute(select(Dashboard).where(Dashboard.is_default.is_(True)))
    dash = result.scalar_one_or_none()
    if dash is None:
        dash = Dashboard(name="Default Dashboard", is_default=True)
        session.add(dash)
        await session.commit()
        await session.refresh(dash)
    return dash


async def ensure_default_dashboard_items(session: AsyncSession) -> None:
    """Keep the default dashboard's items in sync with every known ProxyHost/Guest.

    Only the default dashboard auto-populates this way - custom dashboards are admin-curated
    and must have services attached explicitly (see attach_item_to_dashboard()).
    """
    dash = await ensure_default_dashboard(session)

    existing_host_ids = set(
        (
            await session.execute(
                select(DashboardItem.proxy_host_id).where(
                    DashboardItem.dashboard_id == dash.id,
                    DashboardItem.proxy_host_id.is_not(None),
                )
            )
        ).scalars()
    )
    all_host_ids = set((await session.execute(select(ProxyHost.id))).scalars())
    for host_id in all_host_ids - existing_host_ids:
        session.add(DashboardItem(dashboard_id=dash.id, proxy_host_id=host_id))

    existing_guest_ids = set(
        (
            await session.execute(
                select(DashboardItem.guest_id).where(
                    DashboardItem.dashboard_id == dash.id, DashboardItem.guest_id.is_not(None)
                )
            )
        ).scalars()
    )
    all_guest_ids = set((await session.execute(select(Guest.id))).scalars())
    for guest_id in all_guest_ids - existing_guest_ids:
        session.add(DashboardItem(dashboard_id=dash.id, guest_id=guest_id))

    existing_custom_ids = set(
        (
            await session.execute(
                select(DashboardItem.custom_service_id).where(
                    DashboardItem.dashboard_id == dash.id,
                    DashboardItem.custom_service_id.is_not(None),
                )
            )
        ).scalars()
    )
    all_custom_ids = set((await session.execute(select(CustomService.id))).scalars())
    for custom_service_id in all_custom_ids - existing_custom_ids:
        session.add(DashboardItem(dashboard_id=dash.id, custom_service_id=custom_service_id))

    await session.commit()


async def resolve_dashboard_for_user(session: AsyncSession, user) -> Dashboard:
    if user.dashboard_id is not None:
        dash = await session.get(Dashboard, user.dashboard_id)
        if dash is not None:
            return dash
    return await ensure_default_dashboard(session)


@dataclass(frozen=True)
class ResolvedDashboardItem:
    """A DashboardItem row expressed via the natural key build_dashboard()'s output uses,
    so app.dashboard_view.apply_dashboard_overrides() can stay a pure function with no DB access.

    custom_name/custom_url/logo_url are resolved from the underlying service's own global columns
    (ProxyHost/Guest/CustomService - see app.db.models), not from the DashboardItem itself: those
    are per-dashboard curation only (visibility/order/category), while identity ("what this
    service is called/linked to/looks like") is global and edited on the "Dienste" admin page."""

    kind: Literal["proxy_host", "guest", "custom_service"]
    key: int | tuple[str, int]  # npm_host_id, (node, vmid), or the CustomService's own id
    item_id: int
    category_id: int | None
    visible: bool
    sort_order: int
    custom_name: str | None
    logo_url: str | None
    custom_url: str | None


async def load_resolved_dashboard_items(
    session: AsyncSession, dashboard_id: int
) -> list[ResolvedDashboardItem]:
    rows = (
        await session.execute(
            select(DashboardItem)
            .where(DashboardItem.dashboard_id == dashboard_id)
            .join(ProxyHost, DashboardItem.proxy_host_id == ProxyHost.id, isouter=True)
            .join(Guest, DashboardItem.guest_id == Guest.id, isouter=True)
            .join(CustomService, DashboardItem.custom_service_id == CustomService.id, isouter=True)
            .add_columns(
                ProxyHost.npm_host_id, ProxyHost.logo_id, ProxyHost.custom_name, ProxyHost.custom_url,
                Guest.node, Guest.vmid, Guest.logo_id, Guest.custom_name, Guest.custom_url,
                CustomService.id, CustomService.name, CustomService.url, CustomService.logo_id,
            )
        )
    ).all()

    resolved: list[ResolvedDashboardItem] = []
    for (
        item, npm_host_id, host_logo_id, host_custom_name, host_custom_url,
        guest_node, guest_vmid, guest_logo_id, guest_custom_name, guest_custom_url,
        cs_id, cs_name, cs_url, cs_logo_id,
    ) in rows:
        if item.proxy_host_id is not None and npm_host_id is not None:
            resolved.append(
                ResolvedDashboardItem(
                    kind="proxy_host",
                    key=npm_host_id,
                    item_id=item.id,
                    category_id=item.category_id,
                    visible=item.visible,
                    sort_order=item.sort_order,
                    custom_name=host_custom_name,
                    logo_url=f"/api/logos/{host_logo_id}/image" if host_logo_id else None,
                    custom_url=host_custom_url,
                )
            )
        elif item.guest_id is not None and guest_node is not None:
            resolved.append(
                ResolvedDashboardItem(
                    kind="guest",
                    key=(guest_node, guest_vmid),
                    item_id=item.id,
                    category_id=item.category_id,
                    visible=item.visible,
                    sort_order=item.sort_order,
                    custom_name=guest_custom_name,
                    logo_url=f"/api/logos/{guest_logo_id}/image" if guest_logo_id else None,
                    custom_url=guest_custom_url,
                )
            )
        elif item.custom_service_id is not None and cs_id is not None:
            resolved.append(
                ResolvedDashboardItem(
                    kind="custom_service",
                    key=cs_id,
                    item_id=item.id,
                    category_id=item.category_id,
                    visible=item.visible,
                    sort_order=item.sort_order,
                    custom_name=cs_name,
                    logo_url=f"/api/logos/{cs_logo_id}/image" if cs_logo_id else None,
                    custom_url=cs_url,
                )
            )
    return resolved


async def load_categories(session: AsyncSession, dashboard_id: int) -> list[dict]:
    rows = (
        await session.execute(
            select(Category)
            .where(Category.dashboard_id == dashboard_id)
            .order_by(Category.sort_order)
        )
    ).scalars()
    return [{"id": c.id, "name": c.name, "sort_order": c.sort_order} for c in rows]


async def attach_item_to_dashboard(
    session: AsyncSession,
    dashboard_id: int,
    *,
    proxy_host_id: int | None = None,
    guest_id: int | None = None,
    custom_service_id: int | None = None,
) -> DashboardItem:
    if sum(x is not None for x in (proxy_host_id, guest_id, custom_service_id)) != 1:
        raise ValueError("exactly one of proxy_host_id/guest_id/custom_service_id must be given")
    item = DashboardItem(
        dashboard_id=dashboard_id,
        proxy_host_id=proxy_host_id,
        guest_id=guest_id,
        custom_service_id=custom_service_id,
    )
    session.add(item)
    await session.commit()
    await session.refresh(item)
    return item
