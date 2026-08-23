"""First-admin bootstrapping, run once at startup before the poll loop starts.

Two independent safety nets ensure the app can never end up with zero admins and no way in:
1. BOOTSTRAP_ADMIN_EMAIL/PASSWORD env vars, applied here if the users table is still empty.
2. OIDC JIT-provisioning (app.auth.oidc.provision_user_from_oidc_claims) makes the very first
   user ever created an admin, covering the case where OIDC is set up before these env vars.
"""
from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.security import hash_password
from app.config import settings
from app.db.models import User


async def ensure_bootstrap_admin(session: AsyncSession) -> None:
    if not (settings.bootstrap_admin_email and settings.bootstrap_admin_password):
        return

    user_count = (await session.execute(select(func.count()).select_from(User))).scalar_one()
    if user_count > 0:
        return

    session.add(
        User(
            email=settings.bootstrap_admin_email,
            password_hash=hash_password(settings.bootstrap_admin_password),
            role="admin",
        )
    )
    await session.commit()
