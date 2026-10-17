# Backlog

Open improvements from a static code review. Nothing here was run or reproduced; items marked **verify** need confirmation before fixing. Delete an item in the same change that fixes it.

Product roadmap: [README.md](README.md#roadmap).

## C. UI

Most items are superseded by the FastAPI + HTMX migration (E1); fix only those that survive it. All items are **verify**: line references are unverified.

| ID | File | Problem | Fix |
|----|------|---------|-----|
| C1 | `ui/common.py`, `ui/pages/transactions.py` | `st.rerun()` right after refresh/save/delete discards success and warning messages. | Keep the outcome in `st.session_state` or use `st.toast` after the rerun. |
| C2 | `ui/app.py` | With transactions but an empty price cache the dashboard says "add a transaction". | Say "refresh prices", or refresh automatically on empty cache. |
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
| D2 | Show YTD/1Y/3Y returns (`period_returns_pct` exists in `core/returns.py`, not yet shown in the UI). |
| D4 | Realized vs. unrealized P/L in the dashboard. |

## E. Multi-user hosted service

Design in [IMPROVEMENTS.md](IMPROVEMENTS.md#2-hosted-multi-user-service). Order matters: E1 first, then E4 and E5.

| ID | Item |
|----|------|
| E1 | Migrate UI to FastAPI + HTMX + Jinja under `src/trackfolio/web/`; remove Streamlit. |
| E2 | Settings from environment variables (pydantic-settings). |
| E4 | `user` table; `user_id` on `transaction`; `PortfolioService` scoped to a user. |
| E5 | Authentication: argon2 password hashing, secure session cookies, CSRF protection, login/logout/register pages. |
| E6 | Authorization tests proving cross-user isolation. |
| E7 | Scheduled shared price-refresh job; remove the per-user refresh button. |
| E8 | Paid or otherwise hosting-safe market data provider behind `PriceProvider`. |
| E9 | Rate limiting on auth and instrument search; persistent global cache for search results (metadata is cached in memory per process today). |
| E10 | Container image, reverse proxy with HTTPS, health endpoint, structured logging without financial data. |
| E11 | Account and data deletion; backup and restore procedure. |
