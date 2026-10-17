# Backlog

Open improvements from a static code review. Nothing here was run or reproduced; items marked **verify** need confirmation before fixing. Delete an item in the same change that fixes it.

Product roadmap: [README.md](README.md#roadmap).

## C. UI

| ID | File | Problem | Fix |
|----|------|---------|-----|
| C4 | `web/templates/_dashboard.html` | Positions table lacks P/L % and EUR P/L. | Add columns in the service. |
| C8 | `web/`, `services/` | Italian warnings built in the service, English errors shown in the page. | Return structured data from the service; translate in the templates. |

## D. Returns and features

| ID | Item |
|----|------|
| D2 | Show YTD/1Y/3Y returns (`period_returns_pct` exists in `core/returns.py`, not yet shown in the UI). |
| D4 | Realized vs. unrealized P/L in the dashboard. |

## E. Multi-user hosted service

Design in [IMPROVEMENTS.md](IMPROVEMENTS.md#2-hosted-multi-user-service). Order matters: E4 before E5.

| ID | Item |
|----|------|
| E2 | Settings from environment variables (pydantic-settings). |
| E4 | `user` table; `user_id` on `transaction`; `PortfolioService` scoped to a user. |
| E5 | Authentication: argon2 password hashing, secure session cookies, CSRF protection, login/logout/register pages. |
| E6 | Authorization tests proving cross-user isolation. |
| E7 | Scheduled shared price-refresh job; remove the per-user refresh button. |
| E8 | Paid or otherwise hosting-safe market data provider behind `PriceProvider`. |
| E9 | Rate limiting on auth and instrument search; persistent global cache for search results (metadata is cached in memory per process today). |
| E10 | Container image, reverse proxy with HTTPS, health endpoint, structured logging without financial data. |
| E11 | Account and data deletion; backup and restore procedure. |
