---
paths:
  - "earnings_iv_crush/live/**"
  - "scripts/paper_trade_ibkr.py"
  - "scripts/run_paper_daily.ps1"
  - "deploy/**"
  - "outputs/live/**"
---

# The order path

This code sends orders to a paper account. Read `docs/FORWARD_TEST_SPEC.md` and
`docs/RUNBOOK.md` before changing it.

- Nothing here runs with a connected gateway unless the team lead asked in this session; show a
  dry-run order list and get an explicit go before any `--transmit`.
- Never create or delete `_private/TRANSMIT_OK`; never remove `outputs/live/HALT` or `STOP`.
- The port guard and `LiveConfig.ib_live_ports` are not edited.
- Every change comes with fake-gateway tests in `tests/live/` (patterns: `test_ladder.py`,
  `test_session.py`, `test_w0_safety.py`). The existing safety tests stay green.
- Order events are written to the log before the harness acts on them; keep that order.
- A dry pass writes only under `outputs/live/dry/` and never reads the live stores.
- Limits that protect the account have no environment override.
- The logs in `outputs/live/` are records: never edit them by hand.
