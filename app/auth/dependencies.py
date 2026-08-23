from __future__ import annotations

from datetime import timedelta

from fastapi import Depends, HTTPException, Request, WebSocket, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.security import hash_session_token
from app.config import settings
from app.db.engine import get_db_session, get_sessionmaker
from app.db.models import Session as SessionModel
from app.db.models import User
from app.db.timeutil import utcnow


async def _resolve_session(
    token: str | None, session: AsyncSession
) -> tuple[User, SessionModel] | None:
    """Shared session-token -> User resolution, used by both get_current_user (HTTP, Request-
    typed) and get_current_user_ws (WebSocket handshake, which has no Request to depend on)."""
    if not token:
        return None
    result = await session.execute(
        select(SessionModel).where(SessionModel.token_hash == hash_session_token(token))
    )
    db_session = result.scalar_one_or_none()
    now = utcnow()
    if db_session is None or db_session.expires_at < now:
        return None

    user = await session.get(User, db_session.user_id)
    if user is None or not user.is_active:
        return None

    lifetime = timedelta(days=settings.session_lifetime_days)
    if db_session.expires_at - now < lifetime / 2:
        db_session.expires_at = now + lifetime
    db_session.last_seen_at = now
    await session.commit()
    return user, db_session


async def get_current_user(
    request: Request,
    session: AsyncSession = Depends(get_db_session),
) -> User:
    resolved = await _resolve_session(request.cookies.get("session"), session)
    if resolved is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "not authenticated")
    user, db_session = resolved
    request.state.session_row = db_session
    return user


async def get_current_user_ws(websocket: WebSocket) -> User | None:
    """Same session-cookie check as get_current_user, adapted for the WebSocket handshake in
    app.main's dashboard_ws - returns None (the route closes the connection itself) rather than
    raising, and opens its own short-lived session rather than depending on get_db_session, since
    a websocket dependency's session would otherwise stay open for the connection's entire
    lifetime instead of just the initial auth check."""
    async with get_sessionmaker()() as session:
        resolved = await _resolve_session(websocket.cookies.get("session"), session)
    return resolved[0] if resolved else None


async def require_admin(user: User = Depends(get_current_user)) -> User:
    if user.role != "admin":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "admin role required")
    return user


async def require_csrf(request: Request, user: User = Depends(get_current_user)) -> None:
    """Double-submit CSRF check. Depends on get_current_user having already populated
    request.state.session_row - FastAPI dependency caching means it only runs once per request
    even though both this and the route's own auth dependency reference it."""
    session_row = getattr(request.state, "session_row", None)
    header_value = request.headers.get("X-CSRF-Token")
    if session_row is None or not header_value or header_value != session_row.csrf_token:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "missing or invalid CSRF token")
