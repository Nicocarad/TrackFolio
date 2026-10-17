# Backlog

Open improvements from a static code review. Nothing here was run or reproduced; items marked **verify** need confirmation before fixing. Delete an item in the same change that fixes it.

Product roadmap: [README.md](README.md#roadmap).

## C. UI

| ID | File | Problem | Fix |
|----|------|---------|-----|
| C8 | `web/routes/transactions.py` | Validation errors raised by `core/` and `services/` (`ValueError`) are English and shown as is in the form. | Raise typed errors with codes and translate them in `web/messages.py`. |

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
