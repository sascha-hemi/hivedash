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
    hash_session_token,
    verify_password,
)
from app.config import settings
from app.db.engine import get_db_session
from app.db.timeutil import utcnow
from app.db.models import Session as SessionModel
from app.db.models import User

router = APIRouter(prefix="/api/auth", tags=["auth"])


def _user_out(user: User) -> dict:
    return {
        "id": user.id,
        "email": user.email,
        "display_name": user.display_name,
        "role": user.role,
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


@router.get("/config")
async def auth_config() -> dict:
    return {"oidc_enabled": settings.oidc_enabled}


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
