# Backlog

Open improvements from a static code review. Nothing here was run or reproduced; items marked **verify** need confirmation before fixing. Delete an item in the same change that fixes it.

Product roadmap: [README.md](README.md#roadmap).

## A. Correctness in `core/`

| ID | File | Problem | Fix |
|----|------|---------|-----|
| A5 | `services/portfolio_service.py` | Deleting a BUY is not validated by replaying the ticker history (`validate_transaction` covers add/edit only). | Replay the ticker history on delete and require quantity ≥ 0 throughout. |
| A6 | `core/metrics.py`, `core/timeseries.py` | Invested capital is a net cash flow; after a profitable exit it can be ≤ 0 and return % is wrong. | Use open-position cost basis, or XIRR/TWR (see D). |
| A10 | `models.py` | `table=True` models do not enforce `gt`/`ge`; tickers not upper-cased; SQLite FKs off. | Always validate via `validate_transaction`; add `CheckConstraint`s and `PRAGMA foreign_keys=ON`. |
| A12 | `models.py`, `core/` | `Transaction.currency` duplicates `Asset.currency` and allows mixed currencies per ticker. | Drop the field and derive the currency from the asset; add a dedicated settlement-currency field only if ever needed. |

## B. Services and data

| ID | File | Problem | Fix |
|----|------|---------|-----|
| B1 | `services/portfolio_service.py`, `repositories/` | `save_asset` commits before `save_transaction`: a failed validation leaves an orphan asset. Each repository function commits on its own. | Repositories only `add`; the service commits once and rolls back on error. |
| B2 | `services/portfolio_service.py` | `refresh_prices` catches only `ValueError`/`RuntimeError`/`TimeoutError`; other provider errors abort the whole refresh. | Catch `Exception` per ticker and log it. |
| B4 | `services/portfolio_service.py` | Refresh always downloads from the first transaction date. | Fetch from the last cached date minus a few days. |
| B5 | `market_data/instrument_search.py` | A lookup can make ~50 sequential requests; no result cache. | Cache results in the DB, build `Asset` from quote data. |
| B8 | `services/portfolio_service.py` | Currency-mismatch check duplicated; `get_asset` called in loops (3 places). | `_check_currency` helper and `get_assets_by_ticker`. |
| B9 | `services/portfolio_service.py` | One missing price or FX series hides the whole dashboard; `continue` on missing FX is dead code; leading NaN and zero rates not handled. | Return partial data with warnings; guard NaN/0. |
| B10 | `db.py`, `config.py` | Engine and data dir created at import; no pragmas (WAL, busy timeout); no migrations; `BASE_CURRENCY` unused while "EUR" is hardcoded. | Lazy engine, pragmas, use `BASE_CURRENCY`, adopt migrations before the schema changes. |
| B12 | `services/portfolio_service.py` | `dashboard_data` (~65 lines) builds holdings inside the service. | Move holdings assembly to `core/`. |

Tests to add:
- `refresh_prices`: provider failure with and without cache, no transactions.
- `dashboard_data`: non-EUR asset, missing FX, missing price cache.
- Save with a currency mismatch; edit with `transaction.id`; edit or delete the only transaction.

## C. UI

Most items are superseded by the FastAPI + HTMX migration (E1); fix only those that survive it. All items are **verify**: line references are unverified.

| ID | File | Problem | Fix |
|----|------|---------|-----|
| C1 | `ui/common.py`, `ui/pages/transactions.py` | `st.rerun()` right after refresh/save/delete discards success and warning messages. | Keep the outcome in `st.session_state` or use `st.toast` after the rerun. |
| C2 | `ui/app.py` | With transactions but an empty price cache the dashboard says "add a transaction". | Say "refresh prices", or refresh automatically on empty cache. |
| C3 | `ui/pages/transactions.py` | The asset is saved before the transaction is validated (see B1). | Pass the `Asset` to `save_transaction` and save it in the same unit of work. |
| C4 | `ui/app.py` | Positions table lacks P/L % and EUR P/L; no number formatting. | Add columns in the service; use `column_config`. |
| C5 | `ui/pages/transactions.py` | Delete without confirmation; selectbox instead of an editable table. | Row selection plus a confirmation dialog. |
| C6 | `ui/pages/transactions.py` | A "search by" radio is needed because ISIN is not auto-detected; chosen candidate pre-fills via `value=` without `key`, so typed text can be lost; stale candidates survive after saving. | Auto-detect ISIN, use `key=` and session state, clear candidates on save, cache search with `st.cache_data`. |
| C7 | `ui/` | Business logic in the UI (asset-save decision, allocation filter); the UI instantiates `YFinanceProvider` on every rerun. | Add `allocation()` and `search_instrument()` to the service; wrap the provider in `st.cache_resource`. |
| C8 | `ui/`, `services/` | Italian warnings built in the service, English errors shown in the UI. | Return structured data from the service; translate in the UI. |
| C9 | `ui/common.py` | Sidebar shows the last price date, not the last refresh time; `init_db()` runs on every rerun. | Store a refresh timestamp; `st.cache_resource` for init. |
| C10 | `ui/` | Deprecated `use_container_width`; repeated session try/finally. | `width="stretch"`; a `service_scope()` context manager. |

## D. Returns and features

| ID | Item |
|----|------|
| D1 | Dividends and coupons. |
| D2 | TWR, XIRR (needs `scipy`), CAGR, YTD/1Y/3Y returns; resolves A6. |
| D3 | `SPLIT` event type. |
| D4 | Realized vs. unrealized P/L in the dashboard. |

## E. Multi-user hosted service

Design in [IMPROVEMENTS.md](IMPROVEMENTS.md#2-hosted-multi-user-service). Order matters: E1 first, E3 before E4 and E5.

| ID | Item |
|----|------|
| E1 | Migrate UI to FastAPI + HTMX + Jinja under `src/trackfolio/web/`; remove Streamlit. |
| E2 | Settings from environment variables (pydantic-settings); drop import-time engine creation (B10). |
| E3 | PostgreSQL support and Alembic migrations. |
| E4 | `user` table; `user_id` on `transaction`; `PortfolioService` scoped to a user. |
| E5 | Authentication: argon2 password hashing, secure session cookies, CSRF protection, login/logout/register pages. |
| E6 | Authorization tests proving cross-user isolation. |
| E7 | Scheduled shared price-refresh job; remove the per-user refresh button. |
| E8 | Paid or otherwise hosting-safe market data provider behind `PriceProvider`. |
| E9 | Rate limiting on auth and instrument search; global cache for search results. |
| E10 | Container image, reverse proxy with HTTPS, health endpoint, structured logging without financial data. |
| E11 | Account and data deletion; backup and restore procedure. |
