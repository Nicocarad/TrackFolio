"""Shared Jinja environment and number formatting."""

from pathlib import Path

from fastapi import Request
from fastapi.templating import Jinja2Templates

from trackfolio.web.messages import warning_text


def _auth_context(request: Request) -> dict[str, str]:
    """Expose the CSRF token and email set by the authentication dependency."""
    return {
        "csrf_token": getattr(request.state, "csrf_token", ""),
        "user_email": getattr(request.state, "user_email", ""),
    }


templates = Jinja2Templates(
    directory=Path(__file__).parent.parent / "templates", context_processors=[_auth_context]
)


def _number(value: float | None, digits: int = 2) -> str:
    if value is None or value != value:  # None or NaN
        return "–"
    return f"{value:,.{digits}f}".replace(",", " ")


templates.env.filters["num"] = _number
templates.env.filters["eur"] = lambda value: f"€ {_number(value)}"


def _percent(value: float | None) -> str:
    text = _number(value)
    return text if text == "–" else f"{text}%"


templates.env.filters["pct"] = _percent
templates.env.filters["warning"] = warning_text
