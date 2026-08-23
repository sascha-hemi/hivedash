"""Combine Nginx Proxy Manager hosts with Proxmox guests into dashboard tiles.

Matching strategy: a proxy host's forward_host is compared against each guest's known IP
addresses, and - case-insensitively - against each guest's own `name` (Proxmox's "name" field
doubles as the actual hostname for the common case of an LXC/VM configured to use it as such, so
an admin pointing NPM at a hostname instead of a raw IP still matches). If either matches, the
service tile is enriched with live VM/LXC stats. Everything that can't be matched is still shown
(as a plain link, or as a bare infrastructure tile) rather than dropped - a failed match should
never hide something that IS there.
"""
from __future__ import annotations

from dataclasses import asdict
from typing import Any

from app.clients.npm import ProxyHost
from app.clients.proxmox import Guest


def _guest_dict(guest: Guest) -> dict[str, Any]:
    d = asdict(guest)
    d.pop("ip_addresses", None)
    return d


def build_dashboard(
    hosts: list[ProxyHost] | None,
    guests: list[Guest] | None,
    npm_error: str | None,
    proxmox_error: str | None,
) -> dict[str, Any]:
    hosts = hosts or []
    guests = guests or []

    # index guests by IP and by name (lowercased, since forward_host's casing isn't guaranteed to
    # match) for O(1) matching either way NPM's forward_host is configured
    ip_to_guest: dict[str, Guest] = {}
    name_to_guest: dict[str, Guest] = {}
    for g in guests:
        for ip in g.ip_addresses:
            ip_to_guest[ip] = g
        name_to_guest[g.name.lower()] = g

    matched_vmids: set[tuple[str, int]] = set()
    services = []
    for host in hosts:
        guest = ip_to_guest.get(host.forward_host) or name_to_guest.get(host.forward_host.lower())
        if guest:
            matched_vmids.add((guest.node, guest.vmid))
        services.append(
            {
                "id": host.id,
                "name": host.primary_domain or host.forward_host,
                "domain_names": host.domain_names,
                "href": host.href,
                "forward_host": host.forward_host,
                "forward_port": host.forward_port,
                "enabled": host.enabled,
                "online": host.online,
                "vm": _guest_dict(guest) if guest else None,
            }
        )
    services.sort(key=lambda s: (s["name"] or "").lower())

    infrastructure = [
        _guest_dict(g) | {"ip_addresses": g.ip_addresses}
        for g in guests
        if (g.node, g.vmid) not in matched_vmids
    ]
    infrastructure.sort(key=lambda g: (g["node"], g["name"].lower()))

    return {
        "services": services,
        "infrastructure": infrastructure,
        "errors": {"npm": npm_error, "proxmox": proxmox_error},
    }
