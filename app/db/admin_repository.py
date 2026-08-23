"""DB queries backing app/routers/admin.py (user management, dashboard curation).

Kept separate from app/db/repository.py, which is the hot-path module used by the poll loop and
GET /api/dashboard - nothing here runs outside an explicit admin action.
"""
from __future__ import annotations

from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.security import hash_password
from app.clients.npm import ProxyHost as ProxyHostDC
from app.clients.proxmox import Guest as GuestDC
from app.db.models import (
    Category,
    CustomService,
    Dashboard,
    DashboardItem,
    Guest,
    Logo,
    ProxyHost,
    User,
)
from app.merge import build_dashboard

_UNSET = object()


# --- users -----------------------------------------------------------------------------


async def list_users(session: AsyncSession) -> list[User]:
    return list((await session.execute(select(User).order_by(User.email))).scalars())


async def create_user(
    session: AsyncSession,
    *,
    email: str,
    password: str | None,
    display_name: str | None,
    role: str,
    dashboard_id: int | None,
) -> User:
    user = User(
        email=email,
        password_hash=hash_password(password) if password else None,
        display_name=display_name,
        role=role,
        dashboard_id=dashboard_id,
    )
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return user


async def update_user(
    session: AsyncSession,
    user_id: int,
    *,
    email: str | None = None,
    password: str | None = None,
    display_name: str | None = None,
    role: str | None = None,
    dashboard_id=_UNSET,
    is_active: bool | None = None,
) -> User:
    user = await session.get(User, user_id)
    if user is None:
        raise ValueError(f"no such user: {user_id}")
    if email is not None:
        user.email = email
    if password is not None:
        user.password_hash = hash_password(password)
    if display_name is not None:
        user.display_name = display_name
    if role is not None:
        user.role = role
    if dashboard_id is not _UNSET:
        user.dashboard_id = dashboard_id
    if is_active is not None:
        user.is_active = is_active
    await session.commit()
    await session.refresh(user)
    return user


async def count_admins(session: AsyncSession, *, excluding_user_id: int | None = None) -> int:
    stmt = select(User).where(User.role == "admin", User.is_active.is_(True))
    if excluding_user_id is not None:
        stmt = stmt.where(User.id != excluding_user_id)
    return len((await session.execute(stmt)).scalars().all())


async def delete_user(session: AsyncSession, user_id: int) -> None:
    user = await session.get(User, user_id)
    if user is None:
        return
    await session.delete(user)
    await session.commit()


# --- dashboards --------------------------------------------------------------------------


async def list_dashboards(session: AsyncSession) -> list[Dashboard]:
    return list((await session.execute(select(Dashboard).order_by(Dashboard.name))).scalars())


async def get_dashboard(session: AsyncSession, dashboard_id: int) -> Dashboard | None:
    return await session.get(Dashboard, dashboard_id)


async def create_dashboard(session: AsyncSession, *, name: str, clone_from: Dashboard) -> Dashboard:
    """New dashboards start as a clone of clone_from's current items (admin-curated from there -
    they do NOT auto-receive newly discovered services the way the default dashboard does).

    Categories are deliberately NOT cloned - copying clone_from's category_id values as-is would
    create references to another dashboard's categories (categories are per-dashboard, never
    shared). The new dashboard starts with all items uncategorized; an admin sets up categories
    fresh on it if wanted."""
    dash = Dashboard(name=name, is_default=False)
    session.add(dash)
    await session.flush()

    source_items = (
        await session.execute(select(DashboardItem).where(DashboardItem.dashboard_id == clone_from.id))
    ).scalars()
    for item in source_items:
        session.add(
            DashboardItem(
                dashboard_id=dash.id,
                proxy_host_id=item.proxy_host_id,
                guest_id=item.guest_id,
                custom_service_id=item.custom_service_id,
                visible=item.visible,
                sort_order=item.sort_order,
            )
        )
    await session.commit()
    await session.refresh(dash)
    return dash


async def rename_dashboard(session: AsyncSession, dashboard_id: int, name: str) -> Dashboard:
    dash = await session.get(Dashboard, dashboard_id)
    if dash is None:
        raise ValueError(f"no such dashboard: {dashboard_id}")
    dash.name = name
    await session.commit()
    await session.refresh(dash)
    return dash


async def set_dashboard_tile_size(session: AsyncSession, dashboard_id: int, tile_size: str) -> Dashboard:
    dash = await session.get(Dashboard, dashboard_id)
    if dash is None:
        raise ValueError(f"no such dashboard: {dashboard_id}")
    dash.tile_size = tile_size
    await session.commit()
    await session.refresh(dash)
    return dash


async def set_default_dashboard(session: AsyncSession, dashboard_id: int) -> Dashboard:
    new_default = await session.get(Dashboard, dashboard_id)
    if new_default is None:
        raise ValueError(f"no such dashboard: {dashboard_id}")
    previous = (
        await session.execute(select(Dashboard).where(Dashboard.is_default.is_(True)))
    ).scalar_one_or_none()
    if previous is not None and previous.id != dashboard_id:
        previous.is_default = False
        await session.flush()
    new_default.is_default = True
    await session.commit()
    await session.refresh(new_default)
    return new_default


async def delete_dashboard(session: AsyncSession, dashboard_id: int) -> None:
    dash = await session.get(Dashboard, dashboard_id)
    if dash is None:
        return
    if dash.is_default:
        raise ValueError("cannot delete the default dashboard")
    await session.delete(dash)
    await session.commit()


async def list_dashboard_items_admin(session: AsyncSession, dashboard_id: int) -> list[dict]:
    """A guest matched to a proxy_host (see app.merge's IP-or-hostname matching) has its OWN
    DashboardItem excluded here - while matched, that item is controlled solely by the proxy
    host's own item and has zero effect on the live dashboard either way (see
    app.dashboard_view's module docstring), so showing it here would just be a second, dead
    "sichtbar"/order/category control that looks like it does something but doesn't. If the match
    ever breaks (e.g. the guest's IP changes), its item reappears here automatically - nothing is
    deleted, this is a pure display-time filter re-evaluated on every call."""
    merged, _, _ = await _load_merged_for_admin(session)
    matched_guest_keys = {
        (vm["node"], vm["vmid"]) for svc in merged["services"] if (vm := svc.get("vm")) is not None
    }

    rows = (
        await session.execute(
            select(DashboardItem)
            .where(DashboardItem.dashboard_id == dashboard_id)
            .join(ProxyHost, DashboardItem.proxy_host_id == ProxyHost.id, isouter=True)
            .join(Guest, DashboardItem.guest_id == Guest.id, isouter=True)
            .join(CustomService, DashboardItem.custom_service_id == CustomService.id, isouter=True)
            .add_columns(ProxyHost, Guest, CustomService)
            .order_by(DashboardItem.sort_order)
        )
    ).all()

    out = []
    for item, host, guest, custom in rows:
        if host is not None:
            kind = "proxy_host"
            label = host.custom_name or (host.domain_names[0] if host.domain_names else host.forward_host)
            service_id, logo_id = host.id, host.logo_id
        elif guest is not None:
            if (guest.node, guest.vmid) in matched_guest_keys:
                continue
            kind = "guest"
            label = guest.custom_name or guest.name
            service_id, logo_id = guest.id, guest.logo_id
        elif custom is not None:
            kind = "custom_service"
            label = custom.name
            service_id, logo_id = custom.id, custom.logo_id
        else:
            continue  # orphaned row (target service since deleted) - shouldn't normally happen
        out.append(
            {
                "item_id": item.id,
                "kind": kind,
                "label": label,
                "visible": item.visible,
                "sort_order": item.sort_order,
                "category_id": item.category_id,
                "service_kind": kind,
                "service_id": service_id,
                "logo_id": logo_id,
            }
        )
    return out


async def update_dashboard_item(
    session: AsyncSession,
    item_id: int,
    *,
    visible: bool | None = None,
    sort_order: int | None = None,
    category_id=_UNSET,
) -> DashboardItem:
    item = await session.get(DashboardItem, item_id)
    if item is None:
        raise ValueError(f"no such dashboard item: {item_id}")
    if visible is not None:
        item.visible = visible
    if sort_order is not None:
        item.sort_order = sort_order
    if category_id is not _UNSET:
        if category_id is not None:
            category = await session.get(Category, category_id)
            if category is None or category.dashboard_id != item.dashboard_id:
                raise ValueError(f"no such category on this dashboard: {category_id}")
        item.category_id = category_id
    await session.commit()
    await session.refresh(item)
    return item


# --- categories --------------------------------------------------------------------------


async def list_categories(session: AsyncSession, dashboard_id: int) -> list[Category]:
    return list(
        (
            await session.execute(
                select(Category)
                .where(Category.dashboard_id == dashboard_id)
                .order_by(Category.sort_order)
            )
        ).scalars()
    )


async def create_category(session: AsyncSession, dashboard_id: int, *, name: str) -> Category:
    max_sort_order = (
        await session.execute(
            select(func.max(Category.sort_order)).where(Category.dashboard_id == dashboard_id)
        )
    ).scalar_one()
    category = Category(
        dashboard_id=dashboard_id,
        name=name,
        sort_order=0 if max_sort_order is None else max_sort_order + 1,
    )
    session.add(category)
    await session.commit()
    await session.refresh(category)
    return category


async def update_category(
    session: AsyncSession,
    dashboard_id: int,
    category_id: int,
    *,
    name: str | None = None,
    sort_order: int | None = None,
) -> Category:
    category = await session.get(Category, category_id)
    if category is None or category.dashboard_id != dashboard_id:
        raise ValueError(f"no such category on this dashboard: {category_id}")
    if name is not None:
        category.name = name
    if sort_order is not None:
        category.sort_order = sort_order
    await session.commit()
    await session.refresh(category)
    return category


async def delete_category(session: AsyncSession, dashboard_id: int, category_id: int) -> None:
    category = await session.get(Category, category_id)
    if category is None or category.dashboard_id != dashboard_id:
        return
    # SQLite doesn't enforce ondelete= here either (see delete_logo's docstring) - null out
    # referencing items explicitly rather than relying on the FK annotation.
    await session.execute(
        update(DashboardItem).where(DashboardItem.category_id == category_id).values(category_id=None)
    )
    await session.delete(category)
    await session.commit()


# --- logo library ------------------------------------------------------------------------


async def list_logos(session: AsyncSession) -> list[Logo]:
    return list((await session.execute(select(Logo).order_by(Logo.name))).scalars())


async def get_logo(session: AsyncSession, logo_id: int) -> Logo | None:
    return await session.get(Logo, logo_id)


async def create_logo(
    session: AsyncSession, *, name: str, keywords: list[str], content_type: str, data: bytes
) -> Logo:
    logo = Logo(name=name, keywords=[k.strip().lower() for k in keywords if k.strip()], content_type=content_type, data=data)
    session.add(logo)
    await session.commit()
    await session.refresh(logo)
    return logo


async def delete_logo(session: AsyncSession, logo_id: int) -> None:
    """SQLite doesn't enforce `ondelete=` unless PRAGMA foreign_keys=ON is set per-connection,
    which this app never does - so references must be nulled out explicitly, not left to the FK
    annotation on the model (which stays for documentation/Postgres-portability only)."""
    await session.execute(update(ProxyHost).where(ProxyHost.logo_id == logo_id).values(logo_id=None))
    await session.execute(update(Guest).where(Guest.logo_id == logo_id).values(logo_id=None))
    await session.execute(
        update(CustomService).where(CustomService.logo_id == logo_id).values(logo_id=None)
    )
    logo = await session.get(Logo, logo_id)
    if logo is not None:
        await session.delete(logo)
    await session.commit()


async def set_service_details(
    session: AsyncSession,
    kind: str,
    service_id: int,
    *,
    custom_name=_UNSET,
    custom_url=_UNSET,
    logo_id=_UNSET,
) -> None:
    """Backing for the "Dienste" admin page's edit row for an auto-discovered (proxy_host/guest)
    service - identity is global, not per-dashboard (see app.dashboard_view's module docstring).
    Custom services (no NPM/Proxmox counterpart) use their own dedicated CRUD below instead, since
    name there is a required core field rather than an optional override."""
    if logo_id is not _UNSET and logo_id is not None and await session.get(Logo, logo_id) is None:
        raise ValueError(f"no such logo: {logo_id}")

    model = ProxyHost if kind == "proxy_host" else Guest
    service = await session.get(model, service_id)
    if service is None:
        raise ValueError(f"no such {kind}: {service_id}")
    if custom_name is not _UNSET:
        service.custom_name = custom_name
    if custom_url is not _UNSET:
        service.custom_url = custom_url
    if logo_id is not _UNSET:
        service.logo_id = logo_id
        # any explicit admin choice here - a specific logo, or deliberately "kein Logo" (None) -
        # must permanently opt this service out of poll-time auto-matching (see logo_locked's
        # docstring on the model); otherwise the very next poll's self-healing COALESCE would
        # silently re-assign a logo the admin just removed.
        service.logo_locked = True
    await session.commit()


# --- custom services (admin-created, no NPM/Proxmox counterpart) -----------------------------


async def list_custom_services(session: AsyncSession) -> list[CustomService]:
    return list(
        (await session.execute(select(CustomService).order_by(CustomService.name))).scalars()
    )


async def create_custom_service(
    session: AsyncSession, *, name: str, url: str | None, logo_id: int | None
) -> CustomService:
    if logo_id is not None and await session.get(Logo, logo_id) is None:
        raise ValueError(f"no such logo: {logo_id}")
    service = CustomService(name=name, url=url, logo_id=logo_id)
    session.add(service)
    await session.flush()

    # appear immediately on the default dashboard, same as a freshly-discovered NPM/Proxmox
    # service - otherwise it wouldn't show up anywhere until the next poll cycle re-syncs it.
    default_dash = (
        await session.execute(select(Dashboard).where(Dashboard.is_default.is_(True)))
    ).scalar_one_or_none()
    if default_dash is not None:
        session.add(DashboardItem(dashboard_id=default_dash.id, custom_service_id=service.id))

    await session.commit()
    await session.refresh(service)
    return service


async def update_custom_service(
    session: AsyncSession,
    service_id: int,
    *,
    name: str | None = None,
    url=_UNSET,
    logo_id=_UNSET,
) -> CustomService:
    service = await session.get(CustomService, service_id)
    if service is None:
        raise ValueError(f"no such custom service: {service_id}")
    if name is not None:
        service.name = name
    if url is not _UNSET:
        service.url = url
    if logo_id is not _UNSET:
        if logo_id is not None and await session.get(Logo, logo_id) is None:
            raise ValueError(f"no such logo: {logo_id}")
        service.logo_id = logo_id
    await session.commit()
    await session.refresh(service)
    return service


async def delete_custom_service(session: AsyncSession, service_id: int) -> None:
    # a DashboardItem must reference exactly one target (see the model's check constraint) - if
    # the custom service goes away, its items must be deleted outright, not nulled out.
    await session.execute(delete(DashboardItem).where(DashboardItem.custom_service_id == service_id))
    service = await session.get(CustomService, service_id)
    if service is not None:
        await session.delete(service)
    await session.commit()


async def _load_merged_for_admin(
    session: AsyncSession,
) -> tuple[dict, list[ProxyHost], list[Guest]]:
    """Shared plumbing for list_discovered_services() and list_dashboard_items_admin(): converts
    every known ProxyHost/Guest ORM row into the dataclasses app.merge.build_dashboard() expects
    and runs the real matching logic - reused, not reimplemented, so neither admin surface can
    ever disagree with the live dashboard (or each other) about what counts as matched."""
    hosts = list((await session.execute(select(ProxyHost).order_by(ProxyHost.id))).scalars())
    guests = list((await session.execute(select(Guest).order_by(Guest.id))).scalars())

    host_dcs = [
        ProxyHostDC(
            id=h.npm_host_id, domain_names=h.domain_names, forward_scheme=h.forward_scheme,
            forward_host=h.forward_host, forward_port=h.forward_port, enabled=h.enabled,
            online=h.online, ssl=h.ssl,
        )
        for h in hosts
    ]
    guest_dcs = [
        GuestDC(
            vmid=g.vmid, name=g.name, node=g.node, kind=g.kind, status=g.status, cpu=g.cpu,
            mem=g.mem, maxmem=g.maxmem, ip_addresses=g.ip_addresses,
        )
        for g in guests
    ]
    merged = build_dashboard(host_dcs, guest_dcs, None, None)
    return merged, hosts, guests


async def list_discovered_services(session: AsyncSession) -> list[dict]:
    """Full identity detail for every known proxy_host/guest, for the "Dienste" admin page.

    Unlike list_available_services (a lightweight kind/id/label picker for attaching a service to
    a dashboard), this always lists every discovered service regardless of whether it's currently
    attached to any dashboard at all, and includes the editable logo/name/url fields.

    A proxy_host matched to a guest folds into a single row rather than appearing twice: editing
    always targets the proxy_host side (custom_name/custom_url/logo_id are the host's own
    columns), but the displayed `label` prefers the guest's own name over the host's NPM subdomain
    - the same default precedence app.dashboard_view applies on the live tile (a domain is often
    auto-generated/opaque; the guest name is what the admin actually calls the thing).
    `secondary_label` carries the host's own NPM-derived name for context in that case, so the
    admin can still tell which proxy host it's tied to."""
    merged, hosts, guests = await _load_merged_for_admin(session)

    hosts_by_npm_id = {h.npm_host_id: h for h in hosts}
    guests_by_key = {(g.node, g.vmid): g for g in guests}

    matched_guest_keys: set[tuple[str, int]] = set()
    out = []
    for svc in merged["services"]:
        host = hosts_by_npm_id[svc["id"]]
        vm = svc.get("vm")
        matched_guest = guests_by_key.get((vm["node"], vm["vmid"])) if vm else None
        if matched_guest is not None:
            matched_guest_keys.add((matched_guest.node, matched_guest.vmid))
        out.append(
            {
                "kind": "proxy_host",
                "id": host.id,
                "label": matched_guest.name if matched_guest is not None else svc["name"],
                "secondary_label": svc["name"] if matched_guest is not None else None,
                "custom_name": host.custom_name,
                "custom_url": host.custom_url,
                "logo_id": host.logo_id,
            }
        )

    for g in guests:
        if (g.node, g.vmid) in matched_guest_keys:
            continue
        out.append(
            {
                "kind": "guest",
                "id": g.id,
                "label": g.name,
                "secondary_label": None,
                "custom_name": g.custom_name,
                "custom_url": g.custom_url,
                "logo_id": g.logo_id,
            }
        )
    return out


async def list_available_services(session: AsyncSession) -> list[dict]:
    """Read-only union of known ProxyHost/Guest/CustomService rows, for the admin 'add to
    dashboard' picker. Discovery of proxy_host/guest still originates solely from the pollers -
    this never creates those; custom services are the one kind admins create directly."""
    hosts = (await session.execute(select(ProxyHost))).scalars()
    guests = (await session.execute(select(Guest))).scalars()
    customs = (await session.execute(select(CustomService))).scalars()
    out = [
        {
            "kind": "proxy_host",
            "id": h.id,
            "label": h.custom_name or (h.domain_names[0] if h.domain_names else h.forward_host),
        }
        for h in hosts
    ]
    out += [
        {"kind": "guest", "id": g.id, "label": g.custom_name or f"{g.name} ({g.node})"}
        for g in guests
    ]
    out += [{"kind": "custom_service", "id": c.id, "label": c.name} for c in customs]
    return out
