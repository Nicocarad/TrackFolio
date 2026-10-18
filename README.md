# TrackFolio

Local-first investment tracker. You enter BUY/SELL transactions by hand; TrackFolio rebuilds your positions, the historical value of the portfolio and its return, all in EUR. Data lives in a local SQLite file. The only external requests are instrument search and market data.

## Quick start

Requires Python 3.14+ and [uv](https://docs.astral.sh/uv/).

```bash
uv sync --extra dev
uv run trackfolio create-user you@example.com --admin   # asks for a password (12+ characters)
TRACKFOLIO_SECURE_COOKIES=false uv run uvicorn trackfolio.web.app:app
```

Open <http://127.0.0.1:8000> and log in. `TRACKFOLIO_SECURE_COOKIES=false` is only for plain-HTTP development; behind HTTPS leave it unset (cookies are `Secure` by default). Add `--reload` while developing.

Accounts are created by an admin from the command line; there is no registration page:

| Command | Effect |
|---------|--------|
| `trackfolio create-user EMAIL [--admin] [--password-stdin]` | Create an account |
| `trackfolio set-password EMAIL` | Reset a password and end the user's sessions |
| `trackfolio change-email OLD NEW` | Change an email |
| `trackfolio list-users` | List accounts |
| `trackfolio refresh-prices` | Refresh the price cache for every ticker held by any user; run it on a timer (see below) |

Prices are never fetched on behalf of a request: run `trackfolio refresh-prices` yourself (or from a timer, e.g. every 15 minutes on weekdays between 09:00 and 22:15 Europe/Rome) after adding the first transactions. It fetches each held ticker once, starting from the last cached date minus 5 days, and exits non-zero only when nothing could be refreshed.

Databases that already contain transactions get a placeholder admin `admin@trackfolio.local` that owns them and cannot log in: run `trackfolio set-password admin@trackfolio.local`, then `trackfolio change-email admin@trackfolio.local you@example.com`.

| Route | Purpose |
|-------|---------|
| `/transactions` | Search an instrument by ISIN or ticker, pick a listing, add / edit / delete transactions |
| `/` | KPIs, positions, allocation, value vs. invested capital |

Checks: `uv run pytest`, `uv run ruff check .`, `uv run ruff format --check .`, `uv run mypy src`.

## Features

- Transaction CRUD with validation: positive quantity, non-negative price and fees, no future dates, no selling more than held on that date. Besides BUY and SELL there are `SPLIT` (quantity = ratio, e.g. 2 for 2-for-1, 0.1 for a 10-to-1 reverse split; price and fees 0) and `DIVIDEND` (quantity = shares, price = gross amount per share, fees = withholding). Transactions use the currency of their asset.
- ISIN lookup (format and check digit validated with `python-stdnum`) via OpenFIGI, with Yahoo Finance search as fallback. An ISIN identifies the instrument, not the listing, so you choose the exchange and ticker. OpenFIGI requests retry on 429/5xx (honoring `Retry-After`); a persistent 429 is reported instead of falling back to Yahoo. Set `OPENFIGI_API_KEY` for higher rate limits. Yahoo requests time out after 10 s; instrument metadata is cached in memory for the life of the process and resolved in parallel.
- Daily closing prices from Yahoo Finance, cached in SQLite. If the source is unreachable the cache is used and the missing tickers are reported.
- Historical FX to EUR (`EUR{CUR}=X`) for prices and invested capital.
- Positions with average cost, price, unrealized P/L (amount, % and EUR), realized P/L and net dividends; portfolio KPIs in EUR with unrealized, realized and dividend totals, and YTD/1Y/3Y time-weighted returns when the history is long enough.

## Architecture

Dependencies flow one way: `web → services → core / repositories / market_data`.

| Path | Role |
|------|------|
| `src/trackfolio/core/` | Pure calculations (no I/O): positions, time series, metrics |
| `src/trackfolio/market_data/` | `PriceProvider` interface, Yahoo Finance provider, ISIN/ticker search |
| `src/trackfolio/repositories/` | Persistence (SQLite or PostgreSQL) for users, assets, transactions, prices, rate-limit events and the search cache |
| `src/trackfolio/services/` | `PortfolioService` (per-user use cases), `AuthService`, `RateLimiter`, shared price refresh: orchestrate DB, providers and `core` |
| `src/trackfolio/web/` | FastAPI app: Jinja templates and HTMX fragments; routes call `services/` only. Plotly is served from the installed package, HTMX is vendored in `static/` |
| `src/trackfolio/migrations/`, `cli.py` | Alembic revisions; the `trackfolio` admin command |
| `deploy/`, `Containerfile` | Container image, Quadlets, Caddy and the host setup script (see Deployment) |
| `tests/` | Unit tests with hand-computed values; network is mocked |
| `.claude/`, `CLAUDE.md` | Claude Code settings, hooks and project rules |

The database is created at `data/trackfolio.db` (git-ignored), in WAL mode with foreign keys enforced. The schema is managed by Alembic (`src/trackfolio/migrations/`) and upgraded automatically at startup. A non-empty SQLite database is copied to `data/trackfolio.db.pre-migration-<timestamp>` before each migration. Settings are read from the environment or a git-ignored dotenv file in the project root (template: `.env.example`): `TRACKFOLIO_DATABASE_URL` (e.g. `postgresql+psycopg://user:pass@host/db`) selects PostgreSQL (12 or later) instead of the local SQLite file, `OPENFIGI_API_KEY` raises the OpenFIGI rate limit, `TRACKFOLIO_SECURE_COOKIES` (default true) and `TRACKFOLIO_SESSION_DAYS` (default 14) control the login cookie.

After changing `models.py`: `uv run alembic revision --autogenerate -m "<change>"`, review the file, then commit it.

<details>
<summary>Data model</summary>

| Table | Columns |
|-------|---------|
| `asset` | `ticker` (PK, provider format e.g. `VWCE.DE`), `isin`, `exchange`, `name`, `currency`, `asset_class` |
| `user` | `id` (PK), `email` (unique), `password_hash` (argon2), `is_admin`, `created_at` |
| `user_session` | `token_hash` (PK, SHA-256 of the cookie token), `user_id` (FK), `csrf_token`, `created_at`, `expires_at` |
| `transaction` | `id` (PK), `user_id` (FK), `date`, `ticker` (FK), `type` (BUY/SELL/SPLIT/DIVIDEND), `quantity`, `price`, `fees`, `notes` |
| `price` | `ticker` + `date` (PK), `close`, `source`, `fetched_at` |
| `rate_event` | `id` (PK), `kind`, `key`, `created_at`: failed logins and searches, for rate limiting |
| `instrument_cache` | `query_key` (PK), `payload` (JSON), `created_at`: search results, valid for 7 days |

FX series are stored in `price` under their Yahoo ticker.

</details>

<details>
<summary>Calculation rules</summary>

- **Average cost (PMC):** BUY → `(q_old·pmc_old + q·p + fees) / (q_old + q)`; SELL leaves it unchanged.
- **Realized P/L (SELL):** `q·(p − pmc) − fees`. **Unrealized:** `qty·(price − pmc)`.
- **Value(t):** `Σ qty_i(t) · price_i(t) · fx_i(t)` on business days, prices forward-filled.
- **Net invested capital:** cumulative BUY `(amount + fees)` minus SELL and DIVIDEND `(amount − fees)`, in EUR: a dividend counts as cash returned, so it lowers invested capital and raises TWR/XIRR.
- **Split:** quantity × ratio, average cost ÷ ratio, total cost and realized P/L unchanged. Provider closes are split-adjusted, so history values pre-split shares multiplied by the ratios of later splits.
- **EUR amounts per position:** converted at the latest FX rate, including realized P/L and dividends earned earlier, so the EUR totals of realized P/L and dividends are approximations; value, invested capital and returns use historical rates.
- **Dividend:** leaves quantity and average cost unchanged; net `qty·price − fees` accumulates in the per-position `dividends` column. Same-day order: SPLIT, BUY, DIVIDEND, SELL.
- **KPIs:** P/L = value − invested capital; return % = P/L / invested capital (unreliable once invested capital is ≤ 0 after a profitable exit).
- **TWR:** chain-linked daily returns `(V_t − flow_t) / V_{t−1} − 1`, flows at end of day. **XIRR:** annualized rate over the dated flows plus the final value (bisection, 365-day year). Period returns (YTD/1Y/3Y) are computed in `core/returns.py`.

</details>

## Design notes

**Web layer.** The UI is a FastAPI app that renders Jinja templates and swaps HTML fragments with HTMX; Plotly draws the charts. It keeps no state between requests, which is what hosting and authentication need, and `core/` and `services/` know nothing about it, so the same logic could later serve another frontend.

```mermaid
flowchart LR
    Browser --> Proxy["Caddy (HTTPS)"]
    Proxy --> App["FastAPI + HTMX"]
    App --> PG[("PostgreSQL")]
    Timer["systemd timer: refresh-prices"] --> PG
    Timer --> Provider["Market data provider"]
```

| Choice | Why |
|--------|-----|
| `web → services → core` with a pure `core/` | Financial logic is testable without a database or a browser |
| `PriceProvider` interface | yfinance is unofficial and may need replacing |
| Prices cached in the database; fall back to the cache on network errors | Works through provider outages; failures stay visible as warnings |
| One shared price job, never a provider call per request | A request cannot be slowed or blocked by the provider, and users cannot trigger provider traffic |
| `asset` and `price` shared, everything else per user | Market data is public; every transaction query is scoped to a user and other users' rows behave as missing |
| Server-side sessions, hashed token at rest | A session can be revoked (logout, password reset) |
| Domain errors with a code, translated in the web layer | Services and `core` stay language-neutral |
| SQLModel, Alembic, uv, ruff, mypy strict | Typed models that work on SQLite and PostgreSQL; reproducible tooling |

## Deployment

`deploy/setup.sh` provisions a fresh Oracle Linux 10 host (x86_64 or aarch64) as root; everything then runs rootless as the user `trackfolio`:

```bash
sudo TRACKFOLIO_DOMAIN=trackfolio.example.com bash deploy/setup.sh
```

Without `TRACKFOLIO_DOMAIN` the site is served over plain HTTP on port 80 with non-`Secure` cookies: enough to test the stack, not to use it. Re-run with the domain once DNS points at the host.

| Piece | Where | Notes |
|-------|-------|-------|
| App image | `Containerfile` | Built on the host; runs read-only, no capabilities, as an unprivileged user |
| PostgreSQL 17, app, Caddy | `deploy/quadlet/` | Podman Quadlets; database and app share a private network, the app is published on `127.0.0.1:8000` only |
| HTTPS | `deploy/caddy/` | Caddy on the host network (rootless podman hides client IPs behind a bridge network) listening on 8080/8443, with firewalld forwarding 80/443; automatic certificates for `$TRACKFOLIO_DOMAIN`; security headers, 1 MB body limit |
| Price refresh | `deploy/systemd/trackfolio-refresh.timer` | `trackfolio refresh-prices` every 15 minutes, weekdays 09:00-22:15 Europe/Rome |
| Secrets | `~trackfolio/trackfolio/*.env` (mode 600) | Generated on first run, never overwritten, never printed |
| Health and logs | `GET /health`, stdout | JSON lines with method, path (no query string), status and duration only |

Login is blocked with HTTP 429 (and a `Retry-After` header) after 5 failed attempts for the same email and client IP, 20 from one IP, or 30 for one email within 15 minutes; the per-pair limit keeps an attacker from locking a user out of their own account from another address, and 30 failures on one email still block everyone for up to 15 minutes. Instrument search is limited to 30 requests per user per 10 minutes. The per-IP limit relies on uvicorn's `--proxy-headers` (set in the `Containerfile`; the app container is reachable only through Caddy) and on Caddy preserving the `Host` header, which the origin check also needs. Instrument search results are cached in the database for 7 days.

Re-run the script to deploy new code. After it finishes, point a DNS A record at the host, open ports 80/443 (tcp) and 443 (udp) in the cloud network security list, and create the first administrator as the script prints.

> [!NOTE]
> Verified on an Oracle Linux 10.2 aarch64 VM (1 core, 3.6 GB) without a domain: `setup.sh`, all Quadlet units, the app against PostgreSQL (login, transactions, price refresh job, restart persistence, rate limiting, migrations), and the real client address reaching the app through Caddy from loopback (a client-supplied `X-Forwarded-For` is ignored). Not verified: Let's Encrypt issuance, the client address for traffic arriving from the Internet through firewalld's forward, a reboot, and the pages and charts in a browser behind Caddy. The stack uses about 180 MB of RAM. There is no backup yet: the database lives in the `trackfolio-db` volume only.

## Known limits

**Data and calculations**
- Dividends are entered by hand; there is no automatic reinvestment, withholding tax logic or foreign-currency payout.
- Prices are daily closes and amounts use `float` with a few fixed tolerances such as `1e-9`; `Decimal` is not needed until precision errors appear.
- The value series uses a business-day calendar: exchange holidays are ignored and FX rates carry over weekends.
- `validate_transaction` and `calculate_positions` each replay the transaction history, which duplicates logic.
- A ticker is the asset key: the same instrument on several exchanges is stored as separate assets.
- Amounts are converted to EUR only; there is no other base currency.

**Market data**
- Yahoo Finance is unofficial, may be incomplete or delayed, and its terms and rate limits make it unsuitable for a large public service. A paid provider behind `PriceProvider` is the intended replacement.
- Not every OpenFIGI listing has a Yahoo ticker (enter the ticker manually), and an ISIN search chains several slow Yahoo calls.

**Hosted service**
- There is no registration page, password reset or email: an admin manages accounts with the `trackfolio` command.
- No account or data deletion, and no backup or restore procedure: the database lives in the `trackfolio-db` volume only.
- Rate limits are a brake, not an exact quota (parallel requests can overshoot them), and 30 failed logins on one email block that email for everyone for up to 15 minutes.
- The Content-Security-Policy does not restrict scripts because the pages use inline scripts and Plotly.
- The stack runs on a single host with one app instance; there is no high availability.
- `deploy/setup.sh` is verified by hand on one Oracle Linux 10.2 VM, not by automated tests.

## Roadmap

| Phase | Content | Status |
|-------|---------|--------|
| 1 | Transactions, price cache, positions, value series, base KPIs | Implemented |
| 2 | Dividends, splits, TWR, XIRR | Implemented |
| 3 | Benchmark, volatility, drawdown, Sharpe, correlations, breakdown by asset class/area/currency | Planned |
| 4 | CSV import/export, multi-portfolio, search by name | Planned |
| 5 | Taxes, rebalancing, alerts, scenarios | Planned |
| 6 | FastAPI + HTMX UI, multi-user accounts, authentication, hosted deployment | Implemented (see Deployment and Known limits) |
