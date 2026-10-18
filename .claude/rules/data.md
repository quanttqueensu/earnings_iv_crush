---
paths:
  - "earnings_iv_crush/data/**"
  - "scripts/build/**"
  - "data/**"
---

# Data code

- **Metered.** Builders under `scripts/build/` and the Databento modules can spend money. Price the
  request with the vendor's free cost call, pass a hard `--cap`, get the team lead's go-ahead in
  the session, and reconcile actual spend afterwards. Never start one to "just check".
- **Licensed rows never enter git**, a findings note or a message outside the team
  (`docs/decisions/0004-licensed-data-stays-out-of-git.md`).
- **Fail loudly.** A source that returns nothing raises or prints a funnel; it never falls back
  to an invented value or silently to another source.
- **Check sampling** before pairing snapshots (DoltHub rotates expiries and samples sparsely).
- After building new caches, regenerate the manifest (`python -m earnings_iv_crush.data.sync
  manifest`) and tell the team lead so the bucket can be updated.
