# History

What existed before the team hand-off on 2026-10-18, what was removed, and where it went. This is
provenance, never evidence of what is true now; current state is [`SYSTEM.md`](SYSTEM.md).

## The hand-off reorganisation

- **Research scripts** moved from a flat `scripts/` into `research/<line>/` (closed studies) and
  `scripts/build/` (data builders). Logic was not edited: each moved module's syntax tree matches
  its original once import lines and paths are normalised, and `scripts/validate_screen.py`
  reproduced the twelve-year book byte for byte after the move. A document that cites
  `scripts/<name>.py` means the module of that name in its line folder.
- **Shared research code** promoted into the package: `scripts/market_validate.py` is
  `earnings_iv_crush/research/market_marks.py`, `scripts/validate_skew_oos.py` is
  `earnings_iv_crush/research/gates.py`, `scripts/backfill_forward_window.py` is
  `earnings_iv_crush/research/chains.py`.
- **Pre-registrations** moved from a private folder into `research/<line>/preregs/`, byte for
  byte; their recorded hashes still verify. A pre-registration that cites `_private/<name>.md`
  means the file of that name in its line's `preregs/` folder.
- **Documents.** `documentation/STATUS.md` and `INFRASTRUCTURE.md` were replaced by
  `docs/SYSTEM.md`, `docs/ARCHITECTURE.md`, `docs/DATA.md` and `docs/RUNBOOK.md`.
  `STRATEGY.md`, `SUMMER_SUMMARY.md` and the complete research record moved to `docs/reference/`
  with notes on which sections are superseded.

## Removed

- **The paper radar** (`scripts/paper_radar.py`, `radar_health.py`, `repair_radar_ledger.py`,
  `build_rich_seed.py`, `data/rich_set.csv`, `.github/workflows/paper_radar.yml`, the
  `outputs/paper/` ledger and four tests). Why: [`decisions/0002`](decisions/0002-retire-the-paper-radar.md).
  Recover any of it from git history before this commit.
- **The cross-market adapters** for India (NSE), Brazil (B3) and London Strategic Edge, with their
  tests. Geographic expansion was a clean negative ([`RESEARCH_STATE.md`](RESEARCH_STATE.md)).
  Recover from git history.
- **The legacy entry transmission path.** `scripts/paper_trade_ibkr.py enter` is now a preview
  only; entries transmit only through the `session` ladder.
