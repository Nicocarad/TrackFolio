# Design notes

Architecture and implementation assessment from a static review (nothing was run). Concrete defects are tracked in [BACKLOG.md](BACKLOG.md); this file holds the design direction behind them.

## 1. Web layer: FastAPI + HTMX + Jinja

The UI is a FastAPI app rendering Jinja templates, with HTMX for partial updates and Plotly for charts. It is stateless, which is the prerequisite for hosting and authentication, and `core/` and `services/` stay UI-independent, so the same routes can later serve a SPA or mobile client.

| Path | Role |
|------|------|
| `src/trackfolio/web/app.py` | App factory; runs `init_db()` at startup |
| `src/trackfolio/web/routes/` | Routers (pages and HTMX fragments); call `services/` only |
| `src/trackfolio/web/templates/`, `static/` | Jinja templates, CSS and vendored HTMX |
| `src/trackfolio/web/deps.py` | Dependencies: DB session, provider, service factory |

## 2. Hosted multi-user service

Builds on section 1. Tracked in [BACKLOG.md section E](BACKLOG.md#e-multi-user-hosted-service).

```mermaid
flowchart LR
    Browser --> Proxy[Reverse proxy / HTTPS]
    Proxy --> App[FastAPI + HTMX]
    App --> PG[(PostgreSQL)]
    Job[Scheduled price job] --> PG
    Job --> Provider[Market data provider]
```

| Area | Direction |
|------|-----------|
| Database | PostgreSQL; Alembic migrations (B10) before any schema change. |
| Data ownership | `user` table; `user_id` on `transaction` (and on future per-user tables). `asset` and `price` stay global and shared. Every query filters by user. |
| Service API | `PortfolioService` takes the current user; no global state. |
| Authentication | Email + password with argon2 hashes, server-side sessions in secure cookies (or `fastapi-users`); optional OIDC later. CSRF protection for HTMX forms. |
| Authorization | Isolation tests: user A can never read or modify user B's data. |
| Prices | Scheduled job refreshes shared prices for all held tickers; users never trigger provider calls directly. |
| Market data | Free yfinance is unsuitable for a public service (rate limits, terms of use): put a paid provider behind `PriceProvider`. |
| Instrument search | Rate-limit per user and cache results globally (E9). |
| Configuration | Settings and secrets from environment variables (pydantic-settings); nothing in the repo. |
| Deployment | Container image, reverse proxy with HTTPS, health endpoint, structured logging. |
| Privacy | Account and data deletion, backups, no financial data in logs. |

## Keep

| Choice | Why |
|--------|-----|
| `web → services → core` with a pure `core/` | Financial logic is testable and reusable with another frontend. |
| `PriceProvider` interface | yfinance is unofficial and may need replacing. |
| SQLite price cache, falling back to cache on network errors | Works offline; failures stay visible. |
| SQLModel for models and queries | Typed models; works on SQLite and PostgreSQL. |
| uv, ruff, mypy strict | Reproducible and consistent. |

## Change

| Topic | Issue | Direction |
|-------|-------|-----------|
| Position replay | `validate_transaction` and `calculate_positions` each replay history, which is duplicated logic. | One replay routine in `core/positions.py`, used by both. |
| Instrument lookup | An ISIN search chains many slow, flaky yfinance calls (`Ticker.get_info`, `Search`). | Build `Asset` from search-result data, call `get_info` only for the selected listing, cache the result (E9). |
| Presentation in the service | Italian warning strings built in `services/` (C8). | The service returns structured data; the web layer translates. |
| Money type | `float` with ad hoc tolerances such as `1e-9`. | Keep `float`; centralize tolerances and rounding. Move to `Decimal` only if precision errors appear. |
| Calendar | Business-day index (`freq="B"`) ignores exchange holidays and forward-fills FX across weekends. | Keep; document it in the README if it matters to users. |

## Not now

- **SPA frontend (React/Svelte):** only if HTMX proves insufficient or a mobile app is needed.
- **Ticker as asset primary key:** the same instrument listed on several exchanges becomes separate assets. Revisit with multi-portfolio support.
