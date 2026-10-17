# TrackFolio

Local-first investment tracker. You enter BUY/SELL transactions by hand; TrackFolio rebuilds your positions, the historical value of the portfolio and its return, all in EUR. Data lives in a local SQLite file. The only external requests are instrument search and market data.

## Quick start

Requires Python 3.14+ and [uv](https://docs.astral.sh/uv/).

```bash
uv sync --extra dev
uv run streamlit run src/trackfolio/ui/app.py
```

Open the local URL Streamlit prints.

| Page | Purpose |
|------|---------|
| Transazioni | Search an instrument by ISIN or ticker, pick a listing, add / edit / delete transactions |
| TrackFolio | KPIs, positions, allocation, value vs. invested capital; **Aggiorna prezzi** refreshes the price cache |

Checks: `uv run pytest`, `uv run ruff check .`, `uv run ruff format --check .`, `uv run mypy src`.

## Features

- Transaction CRUD with validation: positive quantity, non-negative price and fees, no future dates, no selling more than held on that date, transaction currency equal to the asset currency.
- ISIN lookup (format and check digit validated with `python-stdnum`) via OpenFIGI, with Yahoo Finance search as fallback. An ISIN identifies the instrument, not the listing, so you choose the exchange and ticker. OpenFIGI requests retry on 429/5xx (honoring `Retry-After`); a persistent 429 is reported instead of falling back to Yahoo. Set `OPENFIGI_API_KEY` for higher rate limits. Yahoo requests time out after 10 s.
- Daily closing prices from Yahoo Finance, cached in SQLite. If the source is unreachable the cache is used and the missing tickers are reported.
- Historical FX to EUR (`EUR{CUR}=X`) for prices and invested capital.
- Positions with average cost, price and unrealized P/L in the instrument currency; portfolio KPIs in EUR.

## Architecture

Dependencies flow one way: `ui → services → core / repositories / market_data`.

| Path | Role |
|------|------|
| `src/trackfolio/core/` | Pure calculations (no I/O): positions, time series, metrics |
| `src/trackfolio/market_data/` | `PriceProvider` interface, Yahoo Finance provider, ISIN/ticker search |
| `src/trackfolio/repositories/` | SQLite persistence for assets, transactions, prices |
| `src/trackfolio/services/` | `PortfolioService`: orchestrates DB, providers and `core` |
| `src/trackfolio/ui/` | Streamlit app and pages; calls `services/` only |
| `tests/` | Unit tests with hand-computed values; network is mocked |
| `BACKLOG.md`, `IMPROVEMENTS.md` | Open defects and design direction from code review |
| `.claude/`, `CLAUDE.md` | Claude Code settings, hooks and project rules |

The database is created at `data/trackfolio.db` (git-ignored), in WAL mode with foreign keys enforced. The schema is managed by Alembic (`src/trackfolio/migrations/`) and upgraded automatically at startup. A non-empty SQLite database is copied to `data/trackfolio.db.pre-migration-<timestamp>` before each migration. Set `TRACKFOLIO_DATABASE_URL` (e.g. `postgresql+psycopg://user:pass@host/db`) to use PostgreSQL instead of the local SQLite file.

After changing `models.py`: `uv run alembic revision --autogenerate -m "<change>"`, review the file, then commit it.

<details>
<summary>Data model</summary>

| Table | Columns |
|-------|---------|
| `asset` | `ticker` (PK, provider format e.g. `VWCE.DE`), `isin`, `exchange`, `name`, `currency`, `asset_class` |
| `transaction` | `id` (PK), `date`, `ticker` (FK), `type` (BUY/SELL), `quantity`, `price`, `fees`, `currency`, `notes` |
| `price` | `ticker` + `date` (PK), `close`, `source`, `fetched_at` |

FX series are stored in `price` under their Yahoo ticker.

</details>

<details>
<summary>Calculation rules</summary>

- **Average cost (PMC):** BUY → `(q_old·pmc_old + q·p + fees) / (q_old + q)`; SELL leaves it unchanged.
- **Realized P/L (SELL):** `q·(p − pmc) − fees`. **Unrealized:** `qty·(price − pmc)`.
- **Value(t):** `Σ qty_i(t) · price_i(t) · fx_i(t)` on business days, prices forward-filled.
- **Net invested capital:** cumulative BUY `(amount + fees)` minus SELL `(amount − fees)`, in EUR.
- **KPIs:** P/L = value − invested capital; return % = P/L / invested capital (unreliable once invested capital is ≤ 0 after a profitable exit).
- **TWR:** chain-linked daily returns `(V_t − flow_t) / V_{t−1} − 1`, flows at end of day. **XIRR:** annualized rate over the dated flows plus the final value (bisection, 365-day year). Period returns (YTD/1Y/3Y) are computed in `core/returns.py`.

</details>

## Known limits

- Prices only: dividends are ignored, so total return is understated for distributing assets.
- No stock-split events: quantities entered before a split must be adjusted by hand (Yahoo prices are split-adjusted).
- Yahoo Finance is unofficial and free providers can be incomplete or delayed; not every OpenFIGI listing has a Yahoo ticker (enter the ticker manually).
- A ticker is the asset key: the same instrument on several exchanges is stored as separate assets.
- Daily closes only; amounts use `float`.

## Roadmap

| Phase | Content | Status |
|-------|---------|--------|
| 1 | Transactions, price cache, positions, value series, base KPIs | Implemented |
| 2 | Dividends, TWR, XIRR, CAGR, YTD/1Y/3Y returns, realized vs. unrealized P/L | Planned |
| 3 | Benchmark, volatility, drawdown, Sharpe, correlations, breakdown by asset class/area/currency | Planned |
| 4 | CSV import/export, multi-portfolio, search by name | Planned |
| 5 | Taxes, rebalancing, alerts, scenarios | Planned |
| 6 | FastAPI + HTMX UI, multi-user accounts, authentication, hosted deployment (see [BACKLOG.md](BACKLOG.md#e-multi-user-hosted-service)) | Planned |
