"""Login throttling, search throttling and the persistent instrument cache."""

from collections.abc import Generator
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pandas as pd
import pytest
from alembic import command
from helpers import PASSWORD, memory_engine, open_client
from sqlalchemy import Engine, inspect
from sqlmodel import Session, create_engine, func, select

from trackfolio.db import _alembic_config, configure_engine, init_db
from trackfolio.errors import DomainError, ErrorCode
from trackfolio.models import Asset, InstrumentCache, RateEvent
from trackfolio.repositories import instrument_cache
from trackfolio.services import auth_service, portfolio_service
from trackfolio.services.auth_service import AuthService
from trackfolio.services.portfolio_service import PortfolioService
from trackfolio.services.rate_limiter import RateLimiter

T0 = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)


class Clock:
    def __init__(self) -> None:
        self.now = T0

    def __call__(self) -> datetime:
        return self.now


@pytest.fixture
def engine() -> Engine:
    return memory_engine()


@pytest.fixture
def session(engine: Engine) -> Generator[Session]:
    with Session(engine) as db:
        yield db


@pytest.fixture
def clock() -> Clock:
    return Clock()


class CountingProvider:
    def __init__(self) -> None:
        self.calls = 0

    def get_history(self, ticker: str, start: date, end: date) -> pd.Series:
        raise AssertionError("unused")

    def get_asset(self, ticker: str) -> Asset:
        raise AssertionError("unused")

    def search_tickers(self, query: str) -> list[Asset]:
        self.calls += 1
        if query == "none":
            return []
        return [Asset(ticker="ABC", name="Abc", currency="EUR", exchange="MIL")]


# -- rate limiter -------------------------------------------------------------------------


def test_limiter_allows_up_to_the_limit_and_reports_the_wait(
    session: Session, clock: Clock
) -> None:
    limiter = RateLimiter(session, clock)
    window = timedelta(minutes=10)
    for _ in range(3):
        assert limiter.check("k", "a", 3, window) == 0
        limiter.record("k", "a")
        clock.now += timedelta(minutes=1)
    # events at 0, 1, 2 min; now = 3 min; the first one expires at 10 min -> 7 min = 420 s
    assert limiter.check("k", "a", 3, window) == 420
    assert limiter.check("k", "b", 3, window) == 0  # other key
    assert limiter.check("other", "a", 3, window) == 0  # other kind
    clock.now = T0 + timedelta(minutes=10)  # first event leaves the window
    assert limiter.check("k", "a", 3, window) == 0


def test_record_purges_events_older_than_the_longest_window(session: Session, clock: Clock) -> None:
    limiter = RateLimiter(session, clock)
    limiter.record("k", "a")
    clock.now = T0 + timedelta(minutes=15, seconds=1)
    limiter.record("k", "a")
    assert limiter.count("k", "a") == 1


# -- login throttling ---------------------------------------------------------------------


def _fail(auth: AuthService, email: str = "alice@example.com", ip: str = "1.1.1.1") -> None:
    assert auth.login(email, "wrong-wrong-wrong", ip) is None


def test_fifth_failure_is_allowed_and_sixth_attempt_is_blocked(
    session: Session, clock: Clock
) -> None:
    auth = AuthService(session, clock)
    auth.create_user("alice@example.com", PASSWORD)
    for _ in range(5):
        _fail(auth)
    with pytest.raises(DomainError) as blocked:
        auth.login("alice@example.com", PASSWORD, "1.1.1.1")  # even the right password
    assert blocked.value.code == ErrorCode.RATE_LIMITED
    assert blocked.value.params["seconds"] == 900
    # email is normalized: another spelling from the same IP is the same bucket
    with pytest.raises(DomainError):
        auth.login(" ALICE@example.com", PASSWORD, "1.1.1.1")
    # the attacker's IP does not lock the victim out elsewhere, nor other emails on that IP
    assert auth.login("alice@example.com", PASSWORD, "2.2.2.2") is not None
    assert auth.login("bob@example.com", PASSWORD, "1.1.1.1") is None


def test_email_threshold_blocks_everyone_at_the_thirtieth_failure(
    session: Session, clock: Clock
) -> None:
    auth = AuthService(session, clock)
    auth.create_user("alice@example.com", PASSWORD)
    for index in range(29):  # 29 distinct IPs, one failure each: no other limit is reached
        _fail(auth, ip=f"10.0.0.{index}")
    assert auth.login("alice@example.com", PASSWORD, "10.9.9.9") is not None  # still open
    _fail(auth, ip="10.0.0.29")  # 30th failure
    with pytest.raises(DomainError) as blocked:
        auth.login("alice@example.com", PASSWORD, "10.9.9.9")
    assert blocked.value.params["seconds"] == 900


def test_retry_after_is_the_largest_remaining_wait(session: Session, clock: Clock) -> None:
    auth = AuthService(session, clock)
    for _ in range(5):
        _fail(auth)  # pair bucket full at T0
    clock.now = T0 + timedelta(minutes=5)
    for index in range(20):
        _fail(auth, f"u{index}@example.com", "3.3.3.3")  # IP bucket full at T0 + 5 min
    with pytest.raises(DomainError) as blocked:
        auth.login("alice@example.com", PASSWORD, "3.3.3.3")
    assert blocked.value.params["seconds"] == 900  # IP bucket: first event at T0+5 -> 15 min
    with pytest.raises(DomainError) as pair:
        auth.login("alice@example.com", PASSWORD, "1.1.1.1")
    assert pair.value.params["seconds"] == 600  # pair bucket: T0 + 15 min - (T0 + 5 min)


def test_failure_is_recorded_before_verification_and_removed_on_success(
    session: Session, clock: Clock, monkeypatch: pytest.MonkeyPatch
) -> None:
    auth = AuthService(session, clock)
    auth.create_user("alice@example.com", PASSWORD)
    limiter = RateLimiter(session, clock)
    real = auth_service._hasher
    seen: list[int] = []

    class Wrapper:
        def verify(self, *args: str) -> bool:
            seen.append(session.exec(select(func.count()).select_from(RateEvent)).one())
            return real.verify(*args)

        def __getattr__(self, name: str) -> object:
            return getattr(real, name)

    monkeypatch.setattr(auth_service, "_hasher", Wrapper())
    assert auth.login("alice@example.com", PASSWORD, "1.1.1.1") is not None
    assert seen == [3]  # pair, IP and email events already stored during the verification
    assert session.exec(select(func.count()).select_from(RateEvent)).one() == 0
    _fail(auth)
    assert limiter.count(auth_service.LOGIN_KIND_PAIR, "1.1.1.1|alice@example.com") == 1


def test_block_expires_with_the_window(session: Session, clock: Clock) -> None:
    auth = AuthService(session, clock)
    auth.create_user("alice@example.com", PASSWORD)
    for _ in range(5):
        _fail(auth)
    clock.now = T0 + timedelta(seconds=899)
    with pytest.raises(DomainError) as blocked:
        auth.login("alice@example.com", PASSWORD, "1.1.1.1")
    assert blocked.value.params["seconds"] == 1
    clock.now = T0 + timedelta(seconds=900)
    assert auth.login("alice@example.com", PASSWORD, "1.1.1.1") is not None


def test_ip_threshold_blocks_across_emails(session: Session, clock: Clock) -> None:
    auth = AuthService(session, clock)
    for index in range(20):
        _fail(auth, f"user{index}@example.com")
    with pytest.raises(DomainError):
        auth.login("fresh@example.com", PASSWORD, "1.1.1.1")
    assert auth.login("fresh@example.com", PASSWORD, "9.9.9.9") is None  # other IP is fine


def test_blocked_attempt_runs_no_argon2_verification(
    session: Session, clock: Clock, monkeypatch: pytest.MonkeyPatch
) -> None:
    auth = AuthService(session, clock)
    auth.create_user("alice@example.com", PASSWORD)
    for _ in range(5):
        _fail(auth)

    class Spy:
        verifies = 0

        def verify(self, *args: object) -> None:
            Spy.verifies += 1
            raise AssertionError("argon2 must not run for a blocked attempt")

    monkeypatch.setattr(auth_service, "_hasher", Spy())
    for email in ("alice@example.com", "nobody@example.com"):
        if email == "nobody@example.com":
            monkeypatch.undo()  # unknown emails have their own bucket; fill it with the real hasher
            for _ in range(5):
                _fail(auth, email)
            monkeypatch.setattr(auth_service, "_hasher", Spy())
        with pytest.raises(DomainError):
            auth.login(email, PASSWORD, "1.1.1.1")
    assert Spy.verifies == 0


def test_successful_login_is_not_counted(session: Session, clock: Clock) -> None:
    auth = AuthService(session, clock)
    auth.create_user("alice@example.com", PASSWORD)
    for _ in range(4):
        _fail(auth)
    for _ in range(10):
        assert auth.login("alice@example.com", PASSWORD, "1.1.1.1") is not None
    pair = "1.1.1.1|alice@example.com"
    assert RateLimiter(session, clock).count(auth_service.LOGIN_KIND_PAIR, pair) == 4
    _fail(auth)  # 5th failure still allowed


def test_login_page_returns_429_with_retry_after_and_italian_message() -> None:
    engine = memory_engine()
    client = next(open_client(engine))
    with Session(engine) as db:
        AuthService(db).create_user("alice@example.com", PASSWORD)
    for _ in range(5):
        wrong = client.post("/login", data={"email": "alice@example.com", "password": "x" * 12})
        assert wrong.status_code == 401
    blocked = client.post("/login", data={"email": "alice@example.com", "password": PASSWORD})
    assert blocked.status_code == 429
    assert 890 <= int(blocked.headers["Retry-After"]) <= 900
    assert "Troppi tentativi. Riprova tra" in blocked.text
    unknown = client.post("/login", data={"email": "x@example.com", "password": PASSWORD})
    assert unknown.status_code == 401  # other email: not throttled, no hint either way
    for _ in range(5):
        client.post("/login", data={"email": "x@example.com", "password": "x" * 12})
    other = client.post("/login", data={"email": "x@example.com", "password": PASSWORD})
    assert other.status_code == 429
    assert other.text.split("Troppi")[1][:20] == blocked.text.split("Troppi")[1][:20]


def test_throttled_or_failed_login_keeps_the_existing_session() -> None:
    engine = memory_engine()
    client = next(open_client(engine, "alice@example.com"))
    assert client.get("/transactions").status_code == 200
    for _ in range(6):  # five failures, then a throttled attempt
        client.post("/login", data={"email": "alice@example.com", "password": "x" * 12})
    assert client.get("/transactions", follow_redirects=False).status_code == 200


def test_window_longer_than_the_retention_is_rejected(session: Session) -> None:
    with pytest.raises(ValueError):
        RateLimiter(session).check("k", "a", 1, timedelta(minutes=16))


# -- search throttling --------------------------------------------------------------------


def _service(session: Session, provider: CountingProvider, clock: Clock, user: int = 1):
    return PortfolioService(session, provider, user, clock)  # type: ignore[arg-type]


def test_search_is_limited_per_user_within_ten_minutes(session: Session, clock: Clock) -> None:
    provider = CountingProvider()
    first, second = _service(session, provider, clock, 1), _service(session, provider, clock, 2)
    for _ in range(30):
        first.search_instrument("abc")
    with pytest.raises(DomainError) as blocked:
        first.search_instrument("abc")
    assert blocked.value.code == ErrorCode.RATE_LIMITED
    assert blocked.value.params["seconds"] == 600
    second.search_instrument("abc")  # independent user
    clock.now = T0 + timedelta(minutes=10)
    first.search_instrument("abc")


def test_search_limit_shows_an_italian_message_in_the_fragment() -> None:
    engine = memory_engine()
    client = next(open_client(engine, "alice@example.com"))
    with Session(engine) as db:
        for _ in range(30):
            db.add(RateEvent(kind="search", key="1", created_at=datetime.now(UTC)))
        db.commit()
    page = client.get("/transactions/search", params={"q": "abc"})
    assert page.status_code == 200
    assert "Troppi tentativi. Riprova tra" in page.text


# -- persistent instrument cache ----------------------------------------------------------


def test_second_search_is_served_from_the_cache(session: Session, clock: Clock) -> None:
    provider = CountingProvider()
    service = _service(session, provider, clock)
    first = service.search_instrument("  Abc ")
    second = service.search_instrument("abc")
    assert provider.calls == 1
    assert [a.model_dump() for a in second] == [a.model_dump() for a in first]
    assert session.get(InstrumentCache, "q:abc") is not None
    # a new service (another process or user) sees the same cache
    _service(session, provider, clock, 2).search_instrument("ABC")
    assert provider.calls == 1


def test_isin_cache_key_is_normalized(
    session: Session, clock: Clock, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[str] = []

    def fake_search_isin(isin: str, provider: object) -> list[Asset]:
        calls.append(isin)
        return [Asset(ticker="AAPL", name="Apple", currency="USD", isin=isin.upper())]

    monkeypatch.setattr(portfolio_service, "search_isin", fake_search_isin)
    service = _service(session, CountingProvider(), clock)
    service.search_instrument("us0378331005")
    service.search_instrument(" US0378331005 ")
    assert len(calls) == 1
    assert session.get(InstrumentCache, "isin:US0378331005") is not None


def test_cache_entry_expires_after_seven_days(session: Session, clock: Clock) -> None:
    provider = CountingProvider()
    service = _service(session, provider, clock)
    service.search_instrument("abc")
    clock.now = T0 + timedelta(days=7) - timedelta(seconds=1)
    service.search_instrument("abc")
    assert provider.calls == 1
    clock.now = T0 + timedelta(days=7)
    service.search_instrument("abc")
    assert provider.calls == 2
    row = session.get(InstrumentCache, "q:abc")
    assert row is not None
    session.refresh(row)
    assert instrument_cache.get_cached(session, "q:abc", clock.now) is not None


def test_empty_results_are_not_cached(session: Session, clock: Clock) -> None:
    provider = CountingProvider()
    service = _service(session, provider, clock)
    assert service.search_instrument("none") == []
    assert service.search_instrument("none") == []
    assert provider.calls == 2
    assert session.exec(select(InstrumentCache)).all() == []


# -- migration ----------------------------------------------------------------------------


def test_migration_0007_upgrades_and_downgrades_on_sqlite(tmp_path: Path) -> None:
    engine = configure_engine(create_engine(f"sqlite:///{tmp_path / 'm.db'}"))
    init_db(engine)
    assert {"rate_event", "instrument_cache"} <= set(inspect(engine).get_table_names())
    indexed = {tuple(i["column_names"]) for i in inspect(engine).get_indexes("rate_event")}
    assert {("kind",), ("key",)} <= indexed
    config = _alembic_config()
    with engine.begin() as connection:
        config.attributes["connection"] = connection
        command.downgrade(config, "0006")
    names = set(inspect(engine).get_table_names())
    assert "rate_event" not in names and "instrument_cache" not in names
    assert "user_session" in names
    init_db(engine)
    assert "rate_event" in inspect(engine).get_table_names()


def test_corrupt_cache_payload_is_a_miss_and_is_overwritten(session: Session, clock: Clock) -> None:
    for payload in ("not json", '[{"bogus": 1}]', '{"a": 1}', "[1]"):
        session.merge(InstrumentCache(query_key="q:abc", payload=payload, created_at=T0))
        session.commit()
        assert instrument_cache.get_cached(session, "q:abc", T0) is None
    provider = CountingProvider()
    _service(session, provider, clock).search_instrument("abc")
    assert provider.calls == 1
    assert instrument_cache.get_cached(session, "q:abc", T0) is not None


def test_storing_a_result_drops_expired_rows(session: Session, clock: Clock) -> None:
    old = T0 - timedelta(days=8)
    session.add(InstrumentCache(query_key="q:old", payload="[]", created_at=old))
    session.commit()
    _service(session, CountingProvider(), clock).search_instrument("abc")
    keys = {row.query_key for row in session.exec(select(InstrumentCache))}
    assert keys == {"q:abc"}


def test_very_long_queries_skip_the_cache(session: Session, clock: Clock) -> None:
    provider = CountingProvider()
    service = _service(session, provider, clock)
    query = "a" * 119  # key "q:" + 119 chars = 121 > 120
    service.search_instrument(query)
    service.search_instrument(query)
    assert provider.calls == 2
    assert session.exec(select(InstrumentCache)).all() == []
    short = "a" * 118  # key length 120 is cached
    service.search_instrument(short)
    service.search_instrument(short)
    assert provider.calls == 3
