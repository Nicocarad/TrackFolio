"""Persistent cache of instrument search results."""

import json
from datetime import UTC, datetime, timedelta

from sqlmodel import Session, col, delete

from trackfolio.models import Asset, InstrumentCache

TTL = timedelta(days=7)
MAX_KEY_LENGTH = 120


def get_cached(session: Session, key: str, now: datetime) -> list[Asset] | None:
    """Return the cached listings for a key, or None when absent or older than the TTL."""
    row = session.get(InstrumentCache, key)
    if row is None:
        return None
    created = row.created_at if row.created_at.tzinfo else row.created_at.replace(tzinfo=UTC)
    if now - created >= TTL:
        return None
    try:
        return [Asset.model_validate(fields) for fields in json.loads(row.payload)]
    except ValueError, TypeError, KeyError:
        return None  # corrupt row: a miss, overwritten by the next put_cached


def put_cached(session: Session, key: str, found: list[Asset], now: datetime) -> None:
    """Store non-empty results and drop expired rows (the caller commits)."""
    session.exec(delete(InstrumentCache).where(col(InstrumentCache.created_at) <= now - TTL))
    if found and len(key) <= MAX_KEY_LENGTH:
        payload = json.dumps([asset.model_dump() for asset in found])
        session.merge(InstrumentCache(query_key=key, payload=payload, created_at=now))
