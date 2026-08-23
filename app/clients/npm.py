"""Minimal async client for the Nginx Proxy Manager REST API.

Auth: POST /api/tokens {identity, secret} -> {token, expires}
List:  GET /api/nginx/proxy-hosts  (Authorization: Bearer <token>)
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field

import httpx

logger = logging.getLogger("dashboard.npm")


@dataclass
class ProxyHost:
    id: int
    domain_names: list[str]
    forward_scheme: str
    forward_host: str
    forward_port: int
    enabled: bool
    online: bool | None  # meta.nginx_online, None if unknown
    ssl: bool

    @property
    def primary_domain(self) -> str | None:
        return self.domain_names[0] if self.domain_names else None

    @property
    def href(self) -> str | None:
        if not self.primary_domain:
            return None
        scheme = "https" if self.ssl else "http"
        return f"{scheme}://{self.primary_domain}"


class NpmClient:
    def __init__(self, base_url: str, email: str, password: str, verify_ssl: bool = True, timeout: float = 10.0):
        self.base_url = base_url
        self.email = email
        self.password = password
        self.verify_ssl = verify_ssl
        self.timeout = timeout
        self._token: str | None = None
        self._token_expires_at: float = 0.0

    async def _login(self, client: httpx.AsyncClient) -> None:
        resp = await client.post(
            f"{self.base_url}/api/tokens",
            json={"identity": self.email, "secret": self.password},
        )
        resp.raise_for_status()
        data = resp.json()
        self._token = data["token"]
        # NPM tokens are typically valid for a long time (e.g. 1 day by default);
        # refresh a bit early to be safe. Fall back to 1h if 'expires' is missing/odd.
        self._token_expires_at = time.time() + 3600

    async def _ensure_token(self, client: httpx.AsyncClient) -> str:
        if not self._token or time.time() >= self._token_expires_at:
            await self._login(client)
        return self._token  # type: ignore[return-value]

    async def list_proxy_hosts(self) -> list[ProxyHost]:
        async with httpx.AsyncClient(verify=self.verify_ssl, timeout=self.timeout) as client:
            token = await self._ensure_token(client)
            resp = await client.get(
                f"{self.base_url}/api/nginx/proxy-hosts",
                headers={"Authorization": f"Bearer {token}"},
                params={"expand": "owner"},
            )
            if resp.status_code == 401:
                # token expired/invalid server-side; force a fresh login and retry once
                self._token = None
                token = await self._ensure_token(client)
                resp = await client.get(
                    f"{self.base_url}/api/nginx/proxy-hosts",
                    headers={"Authorization": f"Bearer {token}"},
                )
            resp.raise_for_status()
            hosts = []
            for item in resp.json():
                meta = item.get("meta") or {}
                hosts.append(
                    ProxyHost(
                        id=item["id"],
                        domain_names=item.get("domain_names") or [],
                        forward_scheme=item.get("forward_scheme", "http"),
                        forward_host=item.get("forward_host", ""),
                        forward_port=item.get("forward_port", 0),
                        enabled=bool(item.get("enabled", 1)),
                        online=meta.get("nginx_online"),
                        ssl=bool(item.get("certificate_id")),
                    )
                )
            return hosts
