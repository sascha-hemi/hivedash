"""Apply one dashboard's visibility/order/category curation on top of build_dashboard()'s output,
plus admin-created "eigene Dienste" (CustomService rows) that have no NPM/Proxmox counterpart at
all.

Pure function, no I/O - mirrors app.merge.build_dashboard()'s own testability. Callers resolve
DashboardItem rows into app.db.repository.ResolvedDashboardItem (natural-key based) and Category
rows into plain {"id","name","sort_order"} dicts first, so this module never touches the DB or ORM
models directly.

A service/guest with no matching item on the given dashboard is treated as hidden. For the
default dashboard this never happens in practice (the poll loop keeps it fully populated via
app.db.repository.ensure_default_dashboard_items()); for a custom, admin-curated dashboard this is
exactly the desired behavior - newly discovered services don't appear until explicitly attached.

A guest that's embedded as `vm` inside a matched service tile is controlled solely by that
service's own dashboard item for visibility/order/category; the guest's own item (if any) is
irrelevant there, since there is only one combined tile to show or hide. The *logo* is the one
exception: if the proxy host itself has no logo, the tile falls back to its matched guest's logo.
The *name* defaults to the guest's own name rather than the NPM subdomain once matched (a domain
is frequently auto-generated/opaque; the guest name is what the admin actually calls the thing) -
unless the host's `custom_name` is explicitly set, which always wins regardless of match state.

Identity (name/url/logo) is deliberately NOT per-dashboard: `custom_name`/`custom_url`/`logo_url`
on a ResolvedDashboardItem are resolved from the underlying service's own global columns (see
app.db.models and the "Dienste" admin page), not from the dashboard item itself - a service is
called and links to the same thing everywhere it's shown. Only visibility/order/category curation
is per-dashboard.

A `custom_service` item has no `merged["services"]`/`merged["infrastructure"]` counterpart at all
(build_dashboard() never sees it - discovery stays solely NPM/Proxmox's job) - its tile is
synthesized directly from the ResolvedDashboardItem's own fields and grouped alongside services
(type "custom"), since a manually-added link is conceptually closer to a service than to a piece of
Proxmox infrastructure.

Output shape: "Dienste" and "Infrastruktur" are permanent, built-in sections (id=None) that always
render, holding whichever services/guests/custom services aren't in one of the admin's own
categories - they never disappear or get replaced once a custom category exists, unlike an earlier
version of this module that merged them into a single "Nicht kategorisiert" bucket. Custom
categories (id=<Category.id>) render first, in their sort_order, each holding services, guests and
custom services mixed freely - emitted even if currently empty so an admin can drag something into
a freshly-created one - followed by Dienste then Infrastruktur last. With zero custom categories
this naturally degrades to exactly the original two-section layout, in the same order, with the
same content - no special-casing needed.
"""
from __future__ import annotations

from typing import Any

from app.db.repository import ResolvedDashboardItem


def _sort_key(pair: tuple[ResolvedDashboardItem, dict]) -> tuple[int, int]:
    # Services and guests each had their own independent sort_order namespace before categories
    # could mix them together - e.g. ensure_default_dashboard_items() gives every newly-attached
    # item sort_order=0, so a fresh service and a fresh guest can tie. Break ties by item_id so
    # the result is deterministic instead of depending on incidental iteration order.
    item, _ = pair
    return (item.sort_order, item.item_id)


def apply_dashboard_overrides(
    merged: dict[str, Any],
    items: list[ResolvedDashboardItem],
    categories: list[dict[str, Any]],
) -> dict[str, Any]:
    host_items = {i.key: i for i in items if i.kind == "proxy_host"}
    guest_items = {i.key: i for i in items if i.kind == "guest"}
    custom_items = [i for i in items if i.kind == "custom_service"]

    resolved_services: list[tuple[ResolvedDashboardItem, dict]] = []
    for svc in merged["services"]:
        item = host_items.get(svc["id"])
        if item is None or not item.visible:
            continue
        tile = dict(svc)
        if item.custom_name:
            tile["name"] = item.custom_name
        elif tile.get("vm"):
            # matched to a Proxmox guest and no explicit override - prefer the guest's own name
            # over the NPM subdomain as the default (a domain is often auto-generated/opaque,
            # whereas the guest name is what the admin actually calls the VM/LXC).
            tile["name"] = tile["vm"]["name"]
        logo_url = item.logo_url
        if logo_url is None and tile.get("vm"):
            guest_item = guest_items.get((tile["vm"]["node"], tile["vm"]["vmid"]))
            if guest_item is not None:
                logo_url = guest_item.logo_url
        tile["logo_url"] = logo_url
        tile["href"] = item.custom_url or tile.get("href")
        tile["type"] = "service"
        tile["item_id"] = item.item_id
        tile["category_id"] = item.category_id
        resolved_services.append((item, tile))

    resolved_infra: list[tuple[ResolvedDashboardItem, dict]] = []
    for guest in merged["infrastructure"]:
        item = guest_items.get((guest["node"], guest["vmid"]))
        if item is None or not item.visible:
            continue
        tile = dict(guest)
        if item.custom_name:
            tile["name"] = item.custom_name
        tile["logo_url"] = item.logo_url
        tile["href"] = item.custom_url
        tile["type"] = "infrastructure"
        tile["item_id"] = item.item_id
        tile["category_id"] = item.category_id
        resolved_infra.append((item, tile))

    for item in custom_items:
        if not item.visible:
            continue
        tile = {
            "id": item.key,
            "name": item.custom_name,
            "href": item.custom_url,
            "logo_url": item.logo_url,
            "type": "custom",
            "item_id": item.item_id,
            "category_id": item.category_id,
        }
        resolved_services.append((item, tile))

    known_category_ids = {c["id"] for c in categories}
    by_category: dict[int, list[tuple[ResolvedDashboardItem, dict]]] = {
        cid: [] for cid in known_category_ids
    }
    uncategorized_services: list[tuple[ResolvedDashboardItem, dict]] = []
    uncategorized_infra: list[tuple[ResolvedDashboardItem, dict]] = []

    for item, tile in resolved_services:
        # a category_id that doesn't belong to this dashboard (stale/orphaned reference) falls
        # back to uncategorized rather than silently disappearing.
        if item.category_id in known_category_ids:
            by_category[item.category_id].append((item, tile))
        else:
            uncategorized_services.append((item, tile))

    for item, tile in resolved_infra:
        if item.category_id in known_category_ids:
            by_category[item.category_id].append((item, tile))
        else:
            uncategorized_infra.append((item, tile))

    sections = []
    for cat in categories:
        group = sorted(by_category[cat["id"]], key=_sort_key)
        sections.append({"id": cat["id"], "name": cat["name"], "tiles": [t for _, t in group]})

    uncategorized_services.sort(key=_sort_key)
    uncategorized_infra.sort(key=_sort_key)
    sections.append({"id": None, "name": "Dienste", "tiles": [t for _, t in uncategorized_services]})
    sections.append({"id": None, "name": "Infrastruktur", "tiles": [t for _, t in uncategorized_infra]})

    return {"errors": merged["errors"], "sections": sections}
