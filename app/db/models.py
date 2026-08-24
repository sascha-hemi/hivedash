"""SQLAlchemy models.

Two kinds of tables live here:
- identity/auth: User, OidcIdentity, Session
- persisted poll results + dashboard curation: ProxyHost, Guest, CustomService, Dashboard,
  DashboardItem

ProxyHost/Guest intentionally mirror the dataclasses in app.clients.npm/app.clients.proxmox
field-for-field (see app/db/repository.py's load_* helpers) so build_dashboard() in app/merge.py
never has to know these rows exist. CustomService has no such external counterpart - it's a
wholly admin-created "Dienst" (see the "Dienste" admin page) for something that's neither an NPM
proxy host nor a Proxmox guest at all.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    Index,
    JSON,
    LargeBinary,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.timeutil import utcnow as _utcnow


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(unique=True, index=True)
    password_hash: Mapped[str | None] = mapped_column(default=None)
    display_name: Mapped[str | None] = mapped_column(default=None)
    role: Mapped[str] = mapped_column(default="user")  # "admin" | "user"
    is_active: Mapped[bool] = mapped_column(default=True)
    dashboard_id: Mapped[int | None] = mapped_column(
        ForeignKey("dashboards.id", ondelete="SET NULL"), default=None
    )
    # Explicit UI language choice ("de", "en", ...) - NULL means "never chosen, keep
    # auto-detecting from the browser on every load" (see core/locale.service.ts). Deliberately
    # a self-service field: a user sets their own via PATCH /api/auth/me, independent of
    # everything else on this row that only an admin can touch via /api/admin/users.
    locale: Mapped[str | None] = mapped_column(default=None)
    created_at: Mapped[datetime] = mapped_column(default=_utcnow)

    dashboard: Mapped["Dashboard | None"] = relationship(back_populates="users")
    oidc_identities: Mapped[list["OidcIdentity"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )


class OidcIdentity(Base):
    __tablename__ = "oidc_identities"
    __table_args__ = (UniqueConstraint("provider", "subject", name="uq_oidc_provider_subject"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    provider: Mapped[str]
    subject: Mapped[str]
    created_at: Mapped[datetime] = mapped_column(default=_utcnow)

    user: Mapped[User] = relationship(back_populates="oidc_identities")


class Session(Base):
    __tablename__ = "sessions"

    token_hash: Mapped[str] = mapped_column(primary_key=True)
    csrf_token: Mapped[str]
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    created_at: Mapped[datetime] = mapped_column(default=_utcnow)
    expires_at: Mapped[datetime]
    last_seen_at: Mapped[datetime] = mapped_column(default=_utcnow)


class Logo(Base):
    """A single uploaded logo image, matched to services by keyword (see app/logo_matching.py).

    Stored as a DB blob rather than a file on disk: icon-scale files, no orphaned-file cleanup to
    build, and the single-file DB backup/restore story stays unchanged (no second volume).
    """

    __tablename__ = "logos"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str]
    keywords: Mapped[list[str]] = mapped_column(JSON, default=list)  # lowercased match terms
    content_type: Mapped[str]
    data: Mapped[bytes] = mapped_column(LargeBinary)
    created_at: Mapped[datetime] = mapped_column(default=_utcnow)


class ProxyHost(Base):
    """Persisted mirror of app.clients.npm.ProxyHost, keyed by the NPM host id."""

    __tablename__ = "proxy_hosts"

    id: Mapped[int] = mapped_column(primary_key=True)
    npm_host_id: Mapped[int] = mapped_column(unique=True, index=True)
    domain_names: Mapped[list[str]] = mapped_column(JSON, default=list)
    forward_scheme: Mapped[str]
    forward_host: Mapped[str]
    forward_port: Mapped[int]
    enabled: Mapped[bool]
    online: Mapped[bool | None]
    ssl: Mapped[bool]
    logo_id: Mapped[int | None] = mapped_column(
        ForeignKey("logos.id", ondelete="SET NULL"), default=None
    )
    # Once the admin has explicitly set logo_id via the "Dienste" page - to a specific logo OR
    # deliberately to "kein Logo" - the poll loop's auto-matching must never touch logo_id again.
    # Without this flag, "explicitly cleared to no logo" and "never auto-matched yet" are both just
    # logo_id IS NULL, indistinguishable - so the very next poll's "sticky but self-healing"
    # COALESCE (see app.db.repository.upsert_proxy_hosts) would silently re-assign a logo the
    # admin had just removed.
    logo_locked: Mapped[bool] = mapped_column(default=False)
    # Admin-configured, global identity overrides ("what this service is", same idiom as logo_id -
    # not per-dashboard) - edited on the "Dienste" admin page, applied in app.dashboard_view.
    custom_name: Mapped[str | None] = mapped_column(default=None)
    custom_url: Mapped[str | None] = mapped_column(default=None)
    first_seen_at: Mapped[datetime] = mapped_column(default=_utcnow)
    last_seen_at: Mapped[datetime] = mapped_column(default=_utcnow)


class Guest(Base):
    """Persisted mirror of app.clients.proxmox.Guest, keyed by (node, vmid)."""

    __tablename__ = "guests"
    __table_args__ = (UniqueConstraint("node", "vmid", name="uq_guest_node_vmid"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    node: Mapped[str]
    vmid: Mapped[int]
    kind: Mapped[str]  # "qemu" | "lxc"
    name: Mapped[str]
    status: Mapped[str]
    cpu: Mapped[float | None]
    mem: Mapped[int | None]
    maxmem: Mapped[int | None]
    ip_addresses: Mapped[list[str]] = mapped_column(JSON, default=list)
    logo_id: Mapped[int | None] = mapped_column(
        ForeignKey("logos.id", ondelete="SET NULL"), default=None
    )
    logo_locked: Mapped[bool] = mapped_column(default=False)
    custom_name: Mapped[str | None] = mapped_column(default=None)
    custom_url: Mapped[str | None] = mapped_column(default=None)
    first_seen_at: Mapped[datetime] = mapped_column(default=_utcnow)
    last_seen_at: Mapped[datetime] = mapped_column(default=_utcnow)


class CustomService(Base):
    """A wholly admin-created service with no NPM/Proxmox counterpart at all (e.g. a device that's
    neither a proxy host nor a Proxmox guest). Unlike ProxyHost/Guest, discovery never touches this
    table - it exists solely via the "Dienste" admin page's CRUD."""

    __tablename__ = "custom_services"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str]
    url: Mapped[str | None] = mapped_column(default=None)
    logo_id: Mapped[int | None] = mapped_column(
        ForeignKey("logos.id", ondelete="SET NULL"), default=None
    )
    created_at: Mapped[datetime] = mapped_column(default=_utcnow)


class Dashboard(Base):
    __tablename__ = "dashboards"
    __table_args__ = (
        Index(
            "uq_dashboard_single_default",
            "is_default",
            unique=True,
            sqlite_where=text("is_default"),
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str]
    is_default: Mapped[bool] = mapped_column(default=False)
    tile_size: Mapped[str] = mapped_column(default="medium")  # "small" | "medium" | "large"
    created_at: Mapped[datetime] = mapped_column(default=_utcnow)

    users: Mapped[list[User]] = relationship(back_populates="dashboard")
    items: Mapped[list["DashboardItem"]] = relationship(
        back_populates="dashboard", cascade="all, delete-orphan"
    )
    categories: Mapped[list["Category"]] = relationship(
        back_populates="dashboard", cascade="all, delete-orphan"
    )


class Category(Base):
    """Admin-defined, per-dashboard group used to sort tiles beyond the default
    Dienste/Infrastruktur split (see app/dashboard_view.py). Never shared across dashboards,
    unlike Logo - each dashboard curates its own category list."""

    __tablename__ = "categories"

    id: Mapped[int] = mapped_column(primary_key=True)
    dashboard_id: Mapped[int] = mapped_column(ForeignKey("dashboards.id", ondelete="CASCADE"))
    name: Mapped[str]
    sort_order: Mapped[int] = mapped_column(default=0)

    dashboard: Mapped[Dashboard] = relationship(back_populates="categories")


class DashboardItem(Base):
    __tablename__ = "dashboard_items"
    __table_args__ = (
        CheckConstraint(
            "(CASE WHEN proxy_host_id IS NOT NULL THEN 1 ELSE 0 END + "
            "CASE WHEN guest_id IS NOT NULL THEN 1 ELSE 0 END + "
            "CASE WHEN custom_service_id IS NOT NULL THEN 1 ELSE 0 END) = 1",
            name="ck_dashboard_item_exactly_one_target",
        ),
        UniqueConstraint("dashboard_id", "proxy_host_id", name="uq_dashboard_item_proxy_host"),
        UniqueConstraint("dashboard_id", "guest_id", name="uq_dashboard_item_guest"),
        UniqueConstraint("dashboard_id", "custom_service_id", name="uq_dashboard_item_custom_service"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    dashboard_id: Mapped[int] = mapped_column(ForeignKey("dashboards.id", ondelete="CASCADE"))
    proxy_host_id: Mapped[int | None] = mapped_column(
        ForeignKey("proxy_hosts.id", ondelete="CASCADE"), default=None
    )
    guest_id: Mapped[int | None] = mapped_column(
        ForeignKey("guests.id", ondelete="CASCADE"), default=None
    )
    custom_service_id: Mapped[int | None] = mapped_column(
        ForeignKey("custom_services.id", ondelete="CASCADE"), default=None
    )
    category_id: Mapped[int | None] = mapped_column(
        ForeignKey("categories.id", ondelete="SET NULL"), default=None
    )
    visible: Mapped[bool] = mapped_column(default=True)
    sort_order: Mapped[int] = mapped_column(default=0)

    dashboard: Mapped[Dashboard] = relationship(back_populates="items")
