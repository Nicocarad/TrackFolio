"""Database-backed rate limiter: counts recorded events per (kind, key) in a sliding window."""

import math
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

from sqlmodel import Session, col, delete, func, select

from trackfolio.models import RateEvent

# Events older than the longest window in use are dropped when a new one is recorded.
RETENTION = timedelta(minutes=15)


def _utc(value: datetime) -> datetime:
    """SQLite returns naive datetimes; they were stored as UTC."""
    return value if value.tzinfo else value.replace(tzinfo=UTC)


def _now() -> datetime:
    return datetime.now(UTC)


class RateLimiter:
    """Sliding-window limiter; ``record`` commits."""

    def __init__(self, session: Session, clock: Callable[[], datetime] = _now) -> None:
        self.session = session
        self.clock = clock

    def check(self, kind: str, key: str, limit: int, window: timedelta) -> int:
        """Return 0 when another event is allowed, else the seconds until it would be."""
        if window > RETENTION:
            raise ValueError("window exceeds the retention used by the purge")
        now = self.clock()
        stamps = self.session.exec(
            select(RateEvent.created_at)
            .where(
                RateEvent.kind == kind,
                RateEvent.key == key,
                col(RateEvent.created_at) > now - window,
            )
            .order_by(col(RateEvent.created_at))
        ).all()
        if len(stamps) < limit:
            return 0
        # The event that frees a slot is the (count - limit + 1)-th oldest one.
        frees_at = _utc(stamps[len(stamps) - limit]) + window
        return max(1, math.ceil((frees_at - now).total_seconds()))

    def record(self, kind: str, key: str) -> int:
        """Count one event, purge the ones no window can still need, return the event id."""
        now = self.clock()
        self.session.exec(delete(RateEvent).where(col(RateEvent.created_at) <= now - RETENTION))
        event = RateEvent(kind=kind, key=key, created_at=now)
        self.session.add(event)
        self.session.commit()
        assert event.id is not None
        return event.id

    def remove(self, event_ids: list[int]) -> None:
        """Forget recorded events (the caller commits)."""
        self.session.exec(delete(RateEvent).where(col(RateEvent.id).in_(event_ids)))

    def count(self, kind: str, key: str) -> int:
        """Number of stored events for a key."""
        statement = (
            select(func.count())
            .select_from(RateEvent)
            .where(RateEvent.kind == kind, RateEvent.key == key)
        )
        return self.session.exec(statement).one()
