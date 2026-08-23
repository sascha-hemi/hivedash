"""Minimal async client for the Proxmox VE REST API.

Auth: header 'Authorization: PVEAPIToken=USER@REALM!TOKENID=SECRET' (no login step).
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

import httpx

logger = logging.getLogger("dashboard.proxmox")


@dataclass
class Guest:
    vmid: int
    name: str
    node: str
    kind: str  # "qemu" or "lxc"
    status: str  # running / stopped / ...
    cpu: float | None
    mem: int | None
    maxmem: int | None
    ip_addresses: list[str]


class ProxmoxClient:
    def __init__(self, base_url: str, token_id: str, token_secret: str, verify_ssl: bool = False, timeout: float = 10.0):
        self.base_url = base_url
        self.token_id = token_id
        self.token_secret = token_secret
        self.verify_ssl = verify_ssl
        self.timeout = timeout

    def _headers(self) -> dict:
        return {"Authorization": f"PVEAPIToken={self.token_id}={self.token_secret}"}

    async def _get(self, client: httpx.AsyncClient, path: str):
        resp = await client.get(f"{self.base_url}/api2/json{path}", headers=self._headers())
        resp.raise_for_status()
        return resp.json()["data"]

    async def _guest_ips(self, client: httpx.AsyncClient, node: str, vmid: int, kind: str) -> list[str]:
        """Best-effort IP lookup. Requires qemu-guest-agent for VMs; uses the
        interfaces endpoint for LXCs. Silently returns [] if unavailable."""
        try:
            if kind == "qemu":
                data = await self._get(client, f"/nodes/{node}/qemu/{vmid}/agent/network-get-interfaces")
                ips = []
                for iface in data.get("result", []):
                    for addr in iface.get("ip-addresses", []):
                        ip = addr.get("ip-address", "")
                        if addr.get("ip-address-type") == "ipv4" and not ip.startswith("127."):
                            ips.append(ip)
                return ips
            else:  # lxc
                data = await self._get(client, f"/nodes/{node}/lxc/{vmid}/interfaces")
                ips = []
                for iface in data:
                    inet = iface.get("inet", "")
                    ip = inet.split("/")[0] if inet else ""
                    if ip and not ip.startswith("127."):
                        ips.append(ip)
                return ips
        except httpx.HTTPStatusError:
            return []
        except Exception:  # noqa: BLE001 - best effort, never break the poll loop
            return []

    async def list_guests(self, fetch_ips: bool = True) -> list[Guest]:
        guests: list[Guest] = []
        async with httpx.AsyncClient(verify=self.verify_ssl, timeout=self.timeout) as client:
            nodes = await self._get(client, "/nodes")
            for node in nodes:
                node_name = node["node"]
                for kind, path in (("qemu", "qemu"), ("lxc", "lxc")):
                    try:
                        items = await self._get(client, f"/nodes/{node_name}/{path}")
                    except httpx.HTTPStatusError as exc:
                        logger.warning("Failed to list %s on node %s: %s", kind, node_name, exc)
                        continue
                    for item in items:
                        status = item.get("status", "unknown")
                        ips: list[str] = []
                        if fetch_ips and status == "running":
                            ips = await self._guest_ips(client, node_name, item["vmid"], kind)
                        guests.append(
                            Guest(
                                vmid=item["vmid"],
                                name=item.get("name", str(item["vmid"])),
                                node=node_name,
                                kind=kind,
                                status=status,
                                cpu=item.get("cpu"),
                                mem=item.get("mem"),
                                maxmem=item.get("maxmem"),
                                ip_addresses=ips,
                            )
                        )
        return guests
