"""FastAPI dependencies: database session, authentication, CSRF and the portfolio service."""

import hmac
from collections.abc import Iterator
from dataclasses import dataclass
from functools import cache

from fastapi import Depends, HTTPException, Request
from sqlmodel import Session

from trackfolio.db import get_session
from trackfolio.market_data.provider import PriceProvider
from trackfolio.market_data.yfinance_provider import YFinanceProvider
from trackfolio.models import User, UserSession
from trackfolio.services.auth_service import AuthService
from trackfolio.services.portfolio_service import PortfolioService

COOKIE_NAME = "trackfolio_session"
SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}


class NotAuthenticated(Exception):
    """Raised when a request has no valid session; the app redirects to the login page."""


@dataclass(frozen=True)
class AuthContext:
    """The authenticated user and the session that proves it."""

    user: User
    session: UserSession


def get_db() -> Iterator[Session]:
    """Yield one database session per request."""
    with get_session() as session:
        yield session


@cache
def get_provider() -> PriceProvider:
    """Return the shared market-data provider."""
    return YFinanceProvider()


def get_auth(request: Request, session: Session = Depends(get_db)) -> AuthContext:
    """Resolve the session cookie; raise ``NotAuthenticated`` if it is missing or invalid."""
    token = request.cookies.get(COOKIE_NAME)
    resolved = AuthService(session).resolve_session(token) if token else None
    if resolved is None:
        raise NotAuthenticated
    user, user_session = resolved
    request.state.csrf_token = user_session.csrf_token
    request.state.user_email = user.email
    return AuthContext(user, user_session)


def require_csrf(request: Request, auth: AuthContext = Depends(get_auth)) -> None:
    """Authenticate the request and, for unsafe methods, check the CSRF header."""
    if request.method in SAFE_METHODS:
        return
    sent = request.headers.get("X-CSRF-Token", "")
    if not hmac.compare_digest(sent.encode(), auth.session.csrf_token.encode()):
        raise HTTPException(status_code=403, detail="Invalid CSRF token")


def get_service(
    session: Session = Depends(get_db),
    provider: PriceProvider = Depends(get_provider),
    auth: AuthContext = Depends(get_auth),
) -> PortfolioService:
    """Build the portfolio service for the authenticated user."""
    if auth.user.id is None:
        raise NotAuthenticated
    return PortfolioService(session, provider, auth.user.id)
