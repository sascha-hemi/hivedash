from __future__ import annotations

from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user, require_csrf
from app.auth.oidc import oauth, provision_user_from_oidc_claims
from app.auth.security import (
    generate_csrf_token,
    generate_session_token,
    hash_password,
    hash_session_token,
    verify_password,
)
from app.config import settings
from app.db.engine import get_db_session
from app.db.timeutil import utcnow
from app.db.models import Session as SessionModel
from app.db.models import User
from app.search_engines import SEARCH_ENGINES, resolve_search_engine

router = APIRouter(prefix="/api/auth", tags=["auth"])

# Kept in sync with frontend/src/app/i18n's language files - the one place both sides agree on
# which codes are actually supported (a stray value elsewhere in the DB just falls back to
# auto-detect on the frontend, but we don't want *new* invalid values written via the API).
SUPPORTED_LOCALES = {"en", "de", "nl", "es", "fr"}


def _user_out(user: User) -> dict:
    return {
        "id": user.id,
        "email": user.email,
        "display_name": user.display_name,
        "role": user.role,
        "locale": user.locale,
        # False for an OIDC-provisioned account (no local password at all) - the frontend uses
        # this to hide the password-change form entirely rather than show it and fail.
        "has_password": user.password_hash is not None,
        "search_engine": user.search_engine,
    }


async def _start_session(response: Response, session: AsyncSession, user: User) -> None:
    token = generate_session_token()
    csrf_token = generate_csrf_token()
    now = utcnow()
    max_age = settings.session_lifetime_days * 86400

    session.add(
        SessionModel(
            token_hash=hash_session_token(token),
            csrf_token=csrf_token,
            user_id=user.id,
            expires_at=now + timedelta(days=settings.session_lifetime_days),
        )
    )
    await session.commit()

    response.set_cookie(
        "session", token, httponly=True, secure=settings.cookie_secure, samesite="lax",
        max_age=max_age, path="/",
    )
    response.set_cookie(
        "csrf_token", csrf_token, httponly=False, secure=settings.cookie_secure, samesite="lax",
        max_age=max_age, path="/",
    )


class LoginRequest(BaseModel):
    email: str
    password: str


@router.post("/login")
async def login(
    payload: LoginRequest,
    response: Response,
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    result = await session.execute(select(User).where(User.email == payload.email))
    user = result.scalar_one_or_none()

    password_ok = verify_password(payload.password, user.password_hash if user else None)
    if user is None or not user.is_active or not password_ok:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid credentials")

    await _start_session(response, session, user)
    return _user_out(user)


@router.post("/logout", dependencies=[Depends(require_csrf)])
async def logout(
    request: Request,
    response: Response,
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    token = request.cookies.get("session")
    if token:
        await session.execute(
            delete(SessionModel).where(SessionModel.token_hash == hash_session_token(token))
        )
        await session.commit()
    response.delete_cookie("session", path="/")
    response.delete_cookie("csrf_token", path="/")
    return {"status": "ok"}


@router.get("/me")
async def me(user: User = Depends(get_current_user)) -> dict:
    return _user_out(user)


class UpdateMeRequest(BaseModel):
    # None is a valid, meaningful value here (reset to auto-detect) - exclude_unset (not "is None")
    # is what distinguishes "the field was in the request body at all" from "leave it alone".
    locale: str | None = None
    # Changing the password is only ever done together: both must be present, verified against
    # the current hash before being accepted. An OIDC-provisioned account (password_hash is None)
    # can never set one this way - that identity is managed entirely by the SSO provider.
    current_password: str | None = None
    new_password: str | None = None
    # None resets to the instance's SEARCH_ENGINE default, exactly like locale above.
    search_engine: str | None = None


@router.patch("/me", dependencies=[Depends(require_csrf)])
async def update_me(
    payload: UpdateMeRequest,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    """Self-service - a user may only ever change their own locale/password/search_engine here,
    nothing else about their own account (role/email/dashboard stay admin-only via
    /api/admin/users)."""
    fields = payload.model_dump(exclude_unset=True)
    if "locale" in fields:
        locale = fields["locale"]
        if locale is not None and locale not in SUPPORTED_LOCALES:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"unsupported locale: {locale}")
        user.locale = locale
        await session.commit()

    if "new_password" in fields:
        if user.password_hash is None:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "account has no local password (managed via SSO)")
        new_password = fields["new_password"]
        current_password = fields.get("current_password")
        if not current_password or not verify_password(current_password, user.password_hash):
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "current password is incorrect")
        if not new_password:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "new password must not be empty")
        user.password_hash = hash_password(new_password)
        await session.commit()

    if "search_engine" in fields:
        engine = fields["search_engine"]
        if engine is not None and engine not in SEARCH_ENGINES:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"unsupported search engine: {engine}")
        user.search_engine = engine
        await session.commit()

    return _user_out(user)


@router.get("/config")
async def auth_config() -> dict:
    return {
        "oidc_enabled": settings.oidc_enabled,
        "search_engines": SEARCH_ENGINES,
        "default_search_engine": resolve_search_engine(settings.default_search_engine),
    }


@router.get("/oidc/login")
async def oidc_login(request: Request):
    if not settings.oidc_enabled:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "OIDC not configured")
    redirect_uri = f"{settings.public_base_url}/api/auth/oidc/callback"
    return await oauth.oidc.authorize_redirect(request, redirect_uri)


@router.get("/oidc/callback")
async def oidc_callback(
    request: Request,
    session: AsyncSession = Depends(get_db_session),
):
    if not settings.oidc_enabled:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "OIDC not configured")

    token = await oauth.oidc.authorize_access_token(request)
    claims = token.get("userinfo")
    if claims is None:
        claims = await oauth.oidc.userinfo(token=token)

    user = await provision_user_from_oidc_claims(
        session,
        provider="oidc",
        subject=claims["sub"],
        email=claims.get("email"),
        display_name=claims.get("name"),
    )

    response = RedirectResponse(url="/")
    await _start_session(response, session, user)
    return response
