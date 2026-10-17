---
paths:
  - "src/trackfolio/core/**"
  - "tests/**"
---

# Financial logic rules

- `core/` is pure: DataFrames and dataclasses in, out. No DB, network or web imports.
- Every `core/` function has a test with hand-computed expected values.
- Average cost (PMC): BUY adds `qty * price + fees` to cost; SELL leaves PMC unchanged and realizes `qty * (price - PMC) - fees`.
- Net invested capital: cumulative `BUY (amount + fees) - SELL (amount - fees)`, converted to EUR at the transaction-date rate.
- Prices are daily closes in the asset currency; convert to EUR with historical FX (`EUR{CUR}=X`, stored inverted).
- Centralize rounding. Use `float` for now; switch to `Decimal` only if precision errors appear.
- Network providers are always mocked in tests.
