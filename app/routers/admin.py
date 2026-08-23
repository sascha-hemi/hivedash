"""Admin-only API: user management + per-dashboard service curation.

Discovery of *what services exist* still originates solely from the NPM/Proxmox pollers
(app.db.repository) - nothing here creates a ProxyHost/Guest row. This module only manages who
can log in and which already-discovered services show up, in what order, under what name, on
which dashboard.
"""
from __future__ import annotations

from typing import Literal

import httpx
from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from pydantic import BaseModel
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import require_admin, require_csrf
from app.clients import dashboard_icons
from app.db import admin_repository as admin_repo
from app.db import repository
from app.db.engine import get_db_session
from app.db.models import Category, CustomService, Dashboard, Logo, User

_ALLOWED_LOGO_CONTENT_TYPES = {
    "image/png",
    "image/jpeg",
    "image/webp",
    "image/svg+xml",
    "image/gif",
    "image/x-icon",
}
_MAX_LOGO_SIZE_BYTES = 2 * 1024 * 1024

router = APIRouter(prefix="/api/admin", tags=["admin"], dependencies=[Depends(require_admin)])

# CSRF is only meaningful (and only applied) to mutating routes - GETs stay admin-only.
_csrf = Depends(require_csrf)


def _user_out(user: User) -> dict:
    return {
        "id": user.id,
        "email": user.email,
        "display_name": user.display_name,
        "role": user.role,
        "is_active": user.is_active,
        "dashboard_id": user.dashboard_id,
    }


def _dashboard_out(dashboard: Dashboard) -> dict:
    return {
        "id": dashboard.id,
        "name": dashboard.name,
        "is_default": dashboard.is_default,
        "tile_size": dashboard.tile_size,
    }


def _category_out(category: Category) -> dict:
    return {"id": category.id, "name": category.name, "sort_order": category.sort_order}


def _logo_out(logo: Logo) -> dict:
    return {
        "id": logo.id,
        "name": logo.name,
        "keywords": logo.keywords,
        "content_type": logo.content_type,
    }


def _custom_service_out(service: CustomService) -> dict:
    return {"id": service.id, "name": service.name, "url": service.url, "logo_id": service.logo_id}


async def _guard_last_admin(session: AsyncSession, user_id: int) -> None:
    if await admin_repo.count_admins(session, excluding_user_id=user_id) == 0:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "cannot remove the last admin account")


# --- users -----------------------------------------------------------------------------


class UserCreate(BaseModel):
    email: str
    password: str | None = None
    display_name: str | None = None
    role: str = "user"
    dashboard_id: int | None = None


class UserUpdate(BaseModel):
    email: str | None = None
    password: str | None = None
    display_name: str | None = None
    role: str | None = None
    dashboard_id: int | None = None
    is_active: bool | None = None


@router.get("/users")
async def list_users(session: AsyncSession = Depends(get_db_session)) -> list[dict]:
    return [_user_out(u) for u in await admin_repo.list_users(session)]


@router.post("/users", status_code=status.HTTP_201_CREATED, dependencies=[_csrf])
async def create_user(
    payload: UserCreate, session: AsyncSession = Depends(get_db_session)
) -> dict:
    try:
        user = await admin_repo.create_user(
            session,
            email=payload.email,
            password=payload.password,
            display_name=payload.display_name,
            role=payload.role,
            dashboard_id=payload.dashboard_id,
        )
    except IntegrityError:
        await session.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "a user with this email already exists")
    return _user_out(user)


@router.patch("/users/{user_id}", dependencies=[_csrf])
async def update_user(
    user_id: int, payload: UserUpdate, session: AsyncSession = Depends(get_db_session)
) -> dict:
    fields = payload.model_dump(exclude_unset=True)
    if fields.get("role") not in (None, "admin") or fields.get("is_active") is False:
        await _guard_last_admin(session, user_id)
    try:
        user = await admin_repo.update_user(session, user_id, **fields)
    except ValueError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    return _user_out(user)


@router.delete("/users/{user_id}", dependencies=[_csrf])
async def delete_user(user_id: int, session: AsyncSession = Depends(get_db_session)) -> dict:
    await _guard_last_admin(session, user_id)
    await admin_repo.delete_user(session, user_id)
    return {"status": "ok"}


# --- dashboards --------------------------------------------------------------------------


class DashboardCreate(BaseModel):
    name: str
    clone_from_id: int | None = None  # defaults to the current default dashboard


class DashboardUpdate(BaseModel):
    name: str | None = None
    is_default: bool | None = None
    tile_size: Literal["small", "medium", "large"] | None = None


@router.get("/dashboards")
async def list_dashboards(session: AsyncSession = Depends(get_db_session)) -> list[dict]:
    return [_dashboard_out(d) for d in await admin_repo.list_dashboards(session)]


@router.post("/dashboards", status_code=status.HTTP_201_CREATED, dependencies=[_csrf])
async def create_dashboard(
    payload: DashboardCreate, session: AsyncSession = Depends(get_db_session)
) -> dict:
    if payload.clone_from_id is not None:
        source = await admin_repo.get_dashboard(session, payload.clone_from_id)
        if source is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "clone_from_id: no such dashboard")
    else:
        source = await repository.ensure_default_dashboard(session)
    dashboard = await admin_repo.create_dashboard(session, name=payload.name, clone_from=source)
    return _dashboard_out(dashboard)


@router.patch("/dashboards/{dashboard_id}", dependencies=[_csrf])
async def update_dashboard(
    dashboard_id: int, payload: DashboardUpdate, session: AsyncSession = Depends(get_db_session)
) -> dict:
    fields = payload.model_dump(exclude_unset=True)
    try:
        if "name" in fields:
            await admin_repo.rename_dashboard(session, dashboard_id, fields["name"])
        if "tile_size" in fields:
            await admin_repo.set_dashboard_tile_size(session, dashboard_id, fields["tile_size"])
        if fields.get("is_default"):
            await admin_repo.set_default_dashboard(session, dashboard_id)
    except ValueError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc

    dashboard = await admin_repo.get_dashboard(session, dashboard_id)
    if dashboard is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no such dashboard")
    return _dashboard_out(dashboard)


@router.delete("/dashboards/{dashboard_id}", dependencies=[_csrf])
async def delete_dashboard(
    dashboard_id: int, session: AsyncSession = Depends(get_db_session)
) -> dict:
    try:
        await admin_repo.delete_dashboard(session, dashboard_id)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    return {"status": "ok"}


# --- dashboard items ---------------------------------------------------------------------


class DashboardItemUpdate(BaseModel):
    item_id: int
    visible: bool | None = None
    sort_order: int | None = None
    category_id: int | None = None


class AttachItemRequest(BaseModel):
    kind: Literal["proxy_host", "guest", "custom_service"]
    id: int


@router.get("/dashboards/{dashboard_id}/items")
async def list_dashboard_items(
    dashboard_id: int, session: AsyncSession = Depends(get_db_session)
) -> list[dict]:
    return await admin_repo.list_dashboard_items_admin(session, dashboard_id)


@router.patch("/dashboards/{dashboard_id}/items", dependencies=[_csrf])
async def bulk_update_dashboard_items(
    dashboard_id: int,
    payload: list[DashboardItemUpdate],
    session: AsyncSession = Depends(get_db_session),
) -> list[dict]:
    for update in payload:
        fields = {name: getattr(update, name) for name in update.model_fields_set if name != "item_id"}
        try:
            await admin_repo.update_dashboard_item(session, update.item_id, **fields)
        except ValueError as exc:
            raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    return await admin_repo.list_dashboard_items_admin(session, dashboard_id)


@router.post("/dashboards/{dashboard_id}/items", status_code=status.HTTP_201_CREATED, dependencies=[_csrf])
async def attach_dashboard_item(
    dashboard_id: int, payload: AttachItemRequest, session: AsyncSession = Depends(get_db_session)
) -> dict:
    kwargs = {
        "proxy_host": {"proxy_host_id": payload.id},
        "guest": {"guest_id": payload.id},
        "custom_service": {"custom_service_id": payload.id},
    }[payload.kind]
    try:
        item = await repository.attach_item_to_dashboard(session, dashboard_id, **kwargs)
    except IntegrityError as exc:
        await session.rollback()
        raise HTTPException(
            status.HTTP_409_CONFLICT, "this service is already on this dashboard"
        ) from exc
    return {"item_id": item.id}


@router.get("/services")
async def list_available_services(session: AsyncSession = Depends(get_db_session)) -> list[dict]:
    return await admin_repo.list_available_services(session)


@router.get("/services/discovered")
async def list_discovered_services(session: AsyncSession = Depends(get_db_session)) -> list[dict]:
    """Backing for the "Dienste" admin page's auto-discovered-services table - every known
    proxy_host/guest with its current logo/name/url, regardless of dashboard attachment."""
    return await admin_repo.list_discovered_services(session)


# --- categories --------------------------------------------------------------------------


class CategoryCreate(BaseModel):
    name: str


class CategoryUpdate(BaseModel):
    name: str | None = None
    sort_order: int | None = None


@router.get("/dashboards/{dashboard_id}/categories")
async def list_categories(
    dashboard_id: int, session: AsyncSession = Depends(get_db_session)
) -> list[dict]:
    return [_category_out(c) for c in await admin_repo.list_categories(session, dashboard_id)]


@router.post(
    "/dashboards/{dashboard_id}/categories", status_code=status.HTTP_201_CREATED, dependencies=[_csrf]
)
async def create_category(
    dashboard_id: int, payload: CategoryCreate, session: AsyncSession = Depends(get_db_session)
) -> dict:
    category = await admin_repo.create_category(session, dashboard_id, name=payload.name)
    return _category_out(category)


@router.patch("/dashboards/{dashboard_id}/categories/{category_id}", dependencies=[_csrf])
async def update_category(
    dashboard_id: int,
    category_id: int,
    payload: CategoryUpdate,
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    fields = payload.model_dump(exclude_unset=True)
    try:
        category = await admin_repo.update_category(session, dashboard_id, category_id, **fields)
    except ValueError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    return _category_out(category)


@router.delete("/dashboards/{dashboard_id}/categories/{category_id}", dependencies=[_csrf])
async def delete_category(
    dashboard_id: int, category_id: int, session: AsyncSession = Depends(get_db_session)
) -> dict:
    await admin_repo.delete_category(session, dashboard_id, category_id)
    return {"status": "ok"}


class ServiceDetailsUpdate(BaseModel):
    logo_id: int | None = None
    custom_name: str | None = None
    custom_url: str | None = None


@router.patch("/services/{kind}/{service_id}", dependencies=[_csrf])
async def update_service(
    kind: Literal["proxy_host", "guest"],
    service_id: int,
    payload: ServiceDetailsUpdate,
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    """Backing for the "Dienste" admin page's edit row for an auto-discovered service - logo,
    name and link are global identity, not per-dashboard (see app.dashboard_view)."""
    fields = payload.model_dump(exclude_unset=True)
    try:
        await admin_repo.set_service_details(session, kind, service_id, **fields)
    except ValueError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    return {"status": "ok"}


# --- custom services (admin-created, no NPM/Proxmox counterpart) -------------------------


class CustomServiceCreate(BaseModel):
    name: str
    url: str | None = None
    logo_id: int | None = None


class CustomServiceUpdate(BaseModel):
    name: str | None = None
    url: str | None = None
    logo_id: int | None = None


@router.get("/custom-services")
async def list_custom_services(session: AsyncSession = Depends(get_db_session)) -> list[dict]:
    return [_custom_service_out(s) for s in await admin_repo.list_custom_services(session)]


@router.post("/custom-services", status_code=status.HTTP_201_CREATED, dependencies=[_csrf])
async def create_custom_service(
    payload: CustomServiceCreate, session: AsyncSession = Depends(get_db_session)
) -> dict:
    service = await admin_repo.create_custom_service(
        session, name=payload.name, url=payload.url, logo_id=payload.logo_id
    )
    return _custom_service_out(service)


@router.patch("/custom-services/{service_id}", dependencies=[_csrf])
async def update_custom_service(
    service_id: int, payload: CustomServiceUpdate, session: AsyncSession = Depends(get_db_session)
) -> dict:
    fields = payload.model_dump(exclude_unset=True)
    try:
        service = await admin_repo.update_custom_service(session, service_id, **fields)
    except ValueError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    return _custom_service_out(service)


@router.delete("/custom-services/{service_id}", dependencies=[_csrf])
async def delete_custom_service(
    service_id: int, session: AsyncSession = Depends(get_db_session)
) -> dict:
    await admin_repo.delete_custom_service(session, service_id)
    return {"status": "ok"}


# --- logo library ------------------------------------------------------------------------


@router.get("/logos")
async def list_logos(session: AsyncSession = Depends(get_db_session)) -> list[dict]:
    return [_logo_out(logo) for logo in await admin_repo.list_logos(session)]


@router.post("/logos", status_code=status.HTTP_201_CREATED, dependencies=[_csrf])
async def create_logo(
    name: str = Form(...),
    keywords: str = Form(""),
    file: UploadFile = File(...),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    if file.content_type not in _ALLOWED_LOGO_CONTENT_TYPES:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"unsupported image type: {file.content_type}")
    data = await file.read()
    if len(data) > _MAX_LOGO_SIZE_BYTES:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "image too large (max 2MB)")

    logo = await admin_repo.create_logo(
        session,
        name=name,
        keywords=[k for k in keywords.split(",")],
        content_type=file.content_type,
        data=data,
    )
    return _logo_out(logo)


@router.delete("/logos/{logo_id}", dependencies=[_csrf])
async def delete_logo(logo_id: int, session: AsyncSession = Depends(get_db_session)) -> dict:
    await admin_repo.delete_logo(session, logo_id)
    return {"status": "ok"}


@router.get("/logos/catalog/search")
async def search_logo_catalog(q: str = Query(default="")) -> list[dict]:
    try:
        return await dashboard_icons.search_catalog(q)
    except httpx.HTTPError as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, f"Katalog nicht erreichbar: {exc}") from exc


class CatalogImportRequest(BaseModel):
    slug: str


@router.post("/logos/catalog/import", status_code=status.HTTP_201_CREATED, dependencies=[_csrf])
async def import_logo_from_catalog(
    payload: CatalogImportRequest, session: AsyncSession = Depends(get_db_session)
) -> dict:
    try:
        data, content_type, aliases = await dashboard_icons.fetch_icon(payload.slug)
    except httpx.HTTPError as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, f"Katalog nicht erreichbar: {exc}") from exc
    except ValueError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc

    keywords = sorted({payload.slug.lower(), *(a.lower() for a in aliases)})
    logo = await admin_repo.create_logo(
        session, name=payload.slug, keywords=keywords, content_type=content_type, data=data
    )
    return _logo_out(logo)
