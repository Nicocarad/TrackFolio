"""Login and logout."""

from typing import Any

from fastapi import APIRouter, Depends, Form, Request, Response
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlmodel import Session

from trackfolio.config import get_settings
from trackfolio.errors import DomainError, ErrorCode
from trackfolio.services.auth_service import AuthService
from trackfolio.web.deps import COOKIE_NAME, get_db, require_csrf
from trackfolio.web.messages import error_text
from trackfolio.web.routes.templating import templates

router = APIRouter()


@router.get("/login", response_class=HTMLResponse)
def login_page(request: Request) -> Any:
    """Render the login form."""
    return templates.TemplateResponse(request, "login.html", {"error": None})


@router.post("/login", response_class=HTMLResponse)
def login(
    request: Request,
    email: str = Form(),
    password: str = Form(),
    session: Session = Depends(get_db),
) -> Any:
    """Open a session; a generic error never reveals whether the email exists."""
    auth = AuthService(session)
    try:
        result = auth.login(email, password, request.client.host if request.client else None)
    except DomainError as error:
        if error.code != ErrorCode.RATE_LIMITED:
            raise
        return templates.TemplateResponse(
            request,
            "login.html",
            {"error": error_text(error)},
            status_code=429,
            headers={"Retry-After": str(error.params["seconds"])},
        )
    if result is None:
        return templates.TemplateResponse(
            request, "login.html", {"error": "Email o password non corrette."}, status_code=401
        )
    previous = request.cookies.get(COOKIE_NAME)
    if previous:
        auth.logout(previous)  # a successful re-login never leaves the old session valid
    response = RedirectResponse("/", status_code=303)
    response.set_cookie(
        COOKIE_NAME,
        result.token,
        max_age=result.max_age_seconds,
        httponly=True,
        samesite="lax",
        secure=get_settings().secure_cookies,
        path="/",
    )
    return response


@router.post("/logout", dependencies=[Depends(require_csrf)])
def logout(request: Request, session: Session = Depends(get_db)) -> Response:
    """End the session and send the browser to the login page."""
    token = request.cookies.get(COOKIE_NAME)
    if token:
        AuthService(session).logout(token)
    response = Response(status_code=204, headers={"HX-Redirect": "/login"})
    response.delete_cookie(COOKIE_NAME, path="/")
    return response
