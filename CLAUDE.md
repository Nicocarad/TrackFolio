# TrackFolio

Local-first portfolio tracker: manual BUY/SELL entry, positions, EUR value history, KPIs. Streamlit + SQLModel/SQLite + yfinance. Spec, architecture and roadmap: [README.md](README.md).

## Commands
- `uv sync --extra dev`
- `uv run streamlit run src/trackfolio/ui/app.py`
- `uv run pytest`
- `uv run ruff check . && uv run ruff format --check .`
- `uv run mypy src`
- `uv run alembic revision --autogenerate -m "<change>"` after editing `models.py`

## Rules
- Layers: `ui -> services -> core / repositories / market_data`. The UI only calls `services/`; no business logic in the UI.
- `core/` stays pure (no I/O). See [.claude/rules/finance.md](.claude/rules/finance.md).
- Market data sits behind `PriceProvider`; mock all network calls in tests.
- Type hints on all public functions (mypy strict); ruff line length 100.
- Run pytest, ruff and mypy after every change and report the results.
- Never commit `data/*.db` or credentials. Never edit `uv.lock` by hand.
- Update README.md in the same change as the code it describes.
- Open work lives in [BACKLOG.md](BACKLOG.md) (design direction in [IMPROVEMENTS.md](IMPROVEMENTS.md)); remove an item in the same change that fixes it.
- Commits: Conventional Commits (`feat:`, `fix:`, `test:`, `docs:`), feature branches `feat/<name>`.
- A hook runs `ruff format` and `ruff check --fix` after each Python edit.
