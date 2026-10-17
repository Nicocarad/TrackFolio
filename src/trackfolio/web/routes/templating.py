"""Shared Jinja environment and number formatting."""

from pathlib import Path

from fastapi.templating import Jinja2Templates

templates = Jinja2Templates(directory=Path(__file__).parent.parent / "templates")


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
