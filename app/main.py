from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import Depends, FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse, Response
from starlette.middleware.sessions import SessionMiddleware
from starlette.websockets import WebSocketState
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user, get_current_user_ws
from app.auth.bootstrap import ensure_bootstrap_admin
from app.auth.routes import router as auth_router
from app.clients.npm import NpmClient
from app.clients.proxmox import ProxmoxClient
from app.config import settings
from app.dashboard_view import apply_dashboard_overrides
from app.db import admin_repository
from app.db import repository
from app.db.engine import get_db_session, get_sessionmaker, init_models
from app.db.models import User
from app.merge import build_dashboard
from app.routers.admin import router as admin_router
from app.spa_static import SPAStaticFiles

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("dashboard")

npm_client = (
    NpmClient(settings.npm_url, settings.npm_email, settings.npm_password, settings.npm_verify_ssl, settings.request_timeout_seconds)
    if settings.npm_enabled
    else None
)
proxmox_client = (
    ProxmoxClient(settings.proxmox_url, settings.proxmox_token_id, settings.proxmox_token_secret, settings.proxmox_verify_ssl, settings.request_timeout_seconds)
    if settings.proxmox_enabled
    else None
)

# Purely diagnostic now - dashboard content itself lives in the DB (see app/db/repository.py),
# not here, so a process restart doesn't lose it.
state: dict = {
    "npm_error": "not polled yet" if npm_client else "NPM not configured",
    "proxmox_error": "not polled yet" if proxmox_client else "Proxmox not configured",
    "generated_at": None,
}


class DashboardConnectionManager:
    """Tracks live /api/ws/dashboard connections so a completed poll can push updates instead of
    every client having to keep re-polling on a timer.

    Different users can be resolved to different dashboards (own tile_size/categories/curation),
    so a push is never one shared payload - each connected socket's own view is recomputed and
    sent individually, same as a fresh GET /api/dashboard would for that user."""

    def __init__(self) -> None:
        self._connections: dict[WebSocket, int] = {}

    def connect(self, websocket: WebSocket, user_id: int) -> None:
        self._connections[websocket] = user_id

    def disconnect(self, websocket: WebSocket) -> None:
        self._connections.pop(websocket, None)

    async def broadcast(self) -> None:
        if not self._connections:
            return
        async with get_sessionmaker()() as session:
            for websocket, user_id in list(self._connections.items()):
                user = await session.get(User, user_id)
                if user is None or not user.is_active:
                    self.disconnect(websocket)
                    continue
                try:
                    payload = await _build_dashboard_payload(session, user)
                    await websocket.send_json(payload)
                except Exception:  # noqa: BLE001 - a dead/misbehaving socket must never break the others
                    self.disconnect(websocket)


ws_manager = DashboardConnectionManager()


async def _build_dashboard_payload(session: AsyncSession, user: User) -> dict:
    dashboard = await repository.resolve_dashboard_for_user(session, user)
    hosts = await repository.load_proxy_hosts(session)
    guests = await repository.load_guests(session)
    merged = build_dashboard(hosts, guests, state["npm_error"], state["proxmox_error"])

    items = await repository.load_resolved_dashboard_items(session, dashboard.id)
    categories = await repository.load_categories(session, dashboard.id)
    view = apply_dashboard_overrides(merged, items, categories)

    return {
        "generated_at": state["generated_at"],
        # the fallback HTTP-polling cadence a client falls back to if the websocket connection
        # can't be established/stays down - deliberately the faster (Proxmox) interval, since
        # that's what actually needs to feel live.
        "poll_interval_seconds": settings.proxmox_poll_interval_seconds,
        "dashboard": {"id": dashboard.id, "name": dashboard.name, "tile_size": dashboard.tile_size},
        **view,
    }


async def poll_npm_once() -> None:
    if not npm_client:
        state["npm_error"] = "NPM not configured"
        return
    try:
        hosts = await npm_client.list_proxy_hosts()
    except Exception as exc:  # noqa: BLE001
        state["npm_error"] = str(exc)
        logger.warning("NPM poll failed: %s", exc)
        return

    async with get_sessionmaker()() as session:
        await repository.upsert_proxy_hosts(session, hosts)
        await repository.ensure_default_dashboard_items(session)

    state["npm_error"] = None
    state["generated_at"] = datetime.now(timezone.utc).isoformat()
    logger.info("NPM poll complete: %d hosts upserted", len(hosts))
    await ws_manager.broadcast()


async def poll_proxmox_once() -> None:
    if not proxmox_client:
        state["proxmox_error"] = "Proxmox not configured"
        return
    try:
        guests = await proxmox_client.list_guests()
    except Exception as exc:  # noqa: BLE001
        state["proxmox_error"] = str(exc)
        logger.warning("Proxmox poll failed: %s", exc)
        return

    async with get_sessionmaker()() as session:
        await repository.upsert_guests(session, guests)
        await repository.ensure_default_dashboard_items(session)

    state["proxmox_error"] = None
    state["generated_at"] = datetime.now(timezone.utc).isoformat()
    logger.info("Proxmox poll complete: %d guests upserted", len(guests))
    await ws_manager.broadcast()


async def npm_poll_loop() -> None:
    while True:
        try:
            await poll_npm_once()
        except Exception:  # noqa: BLE001
            logger.exception("Unexpected error in NPM poll loop")
        await asyncio.sleep(settings.npm_poll_interval_seconds)


async def proxmox_poll_loop() -> None:
    while True:
        try:
            await poll_proxmox_once()
        except Exception:  # noqa: BLE001
            logger.exception("Unexpected error in Proxmox poll loop")
        await asyncio.sleep(settings.proxmox_poll_interval_seconds)


@asynccontextmanager
async def lifespan(_: FastAPI):
    await init_models()
    async with get_sessionmaker()() as session:
        await ensure_bootstrap_admin(session)
        await repository.ensure_default_dashboard(session)

    npm_task = asyncio.create_task(npm_poll_loop())
    proxmox_task = asyncio.create_task(proxmox_poll_loop())
    yield
    npm_task.cancel()
    proxmox_task.cancel()


app = FastAPI(title="HiveDash", lifespan=lifespan)

# Holds only the transient OIDC state/nonce during the login redirect round-trip - not the app's
# own login session, which is DB-backed (see app/auth/routes.py, app/db/models.Session).
app.add_middleware(SessionMiddleware, secret_key=settings.cookie_secret or "dev-only-insecure-secret")

app.include_router(auth_router)
app.include_router(admin_router)


@app.get("/api/dashboard")
async def get_dashboard(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> JSONResponse:
    return JSONResponse(await _build_dashboard_payload(session, user))


@app.websocket("/api/ws/dashboard")
async def dashboard_ws(websocket: WebSocket) -> None:
    """Live push counterpart to GET /api/dashboard - same session cookie, same per-user resolved
    view. Sends one snapshot immediately on connect, then another every time a poll completes
    (see DashboardConnectionManager.broadcast(), called from poll_npm_once()/poll_proxmox_once()).
    Never expects an incoming message itself; receive_text() is only how Starlette surfaces the
    client disconnecting."""
    user = await get_current_user_ws(websocket)
    if user is None:
        await websocket.close(code=1008)  # policy violation - no valid session cookie
        return

    await websocket.accept()
    ws_manager.connect(websocket, user.id)
    try:
        async with get_sessionmaker()() as session:
            await websocket.send_json(await _build_dashboard_payload(session, user))
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        ws_manager.disconnect(websocket)
        if websocket.client_state != WebSocketState.DISCONNECTED:
            await websocket.close()


@app.get("/api/health")
async def health() -> dict:
    return {"status": "ok"}


@app.get("/api/logos/{logo_id}/image")
async def get_logo_image(
    logo_id: int,
    _user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> Response:
    """Deliberately gated by get_current_user only (not require_admin) - any logged-in user
    needs to load tile images, not just admins. Never mounted on admin_router, which admin-gates
    every route registered on it, GETs included."""
    logo = await admin_repository.get_logo(session, logo_id)
    if logo is None:
        raise HTTPException(404, "no such logo")
    return Response(content=logo.data, media_type=logo.content_type)


app.mount("/", SPAStaticFiles(directory="app/static", html=True), name="static")
