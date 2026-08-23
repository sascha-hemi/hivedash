"""Generic OIDC client (Authlib) plus JIT user provisioning on first login.

Config-driven (issuer/client id/secret), not vendor-specific - the concrete target is the
user's own Authentik instance, but any standard OIDC provider works.
"""
from __future__ import annotations

from authlib.integrations.starlette_client import OAuth
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db.models import OidcIdentity, User

oauth = OAuth()

if settings.oidc_enabled:
    oauth.register(
        name="oidc",
        client_id=settings.oidc_client_id,
        client_secret=settings.oidc_client_secret,
        server_metadata_url=f"{settings.oidc_issuer}/.well-known/openid-configuration",
        client_kwargs={"scope": "openid email profile"},
    )


async def provision_user_from_oidc_claims(
    session: AsyncSession,
    *,
    provider: str,
    subject: str,
    email: str | None,
    display_name: str | None,
) -> User:
    """Pure-of-network-IO: takes already-validated claims, does only DB work. Kept separate from
    the redirect/token-exchange handshake in routes.py so it's unit-testable without Authlib/HTTP.
    """
    existing = await session.execute(
        select(OidcIdentity).where(
            OidcIdentity.provider == provider, OidcIdentity.subject == subject
        )
    )
    identity = existing.scalar_one_or_none()
    if identity is not None:
        user = await session.get(User, identity.user_id)
        if user is None:
            raise ValueError(f"OidcIdentity {identity.id} points at a missing user")
        return user

    if not email:
        raise ValueError("OIDC provider did not return an email claim")

    user_count = (await session.execute(select(func.count()).select_from(User))).scalar_one()
    is_first_user = user_count == 0

    result = await session.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()
    if user is None:
        user = User(email=email, display_name=display_name, role="admin" if is_first_user else "user")
        session.add(user)
        await session.flush()

    session.add(OidcIdentity(user_id=user.id, provider=provider, subject=subject))
    await session.commit()
    await session.refresh(user)
    return user
