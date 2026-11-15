# Slate tests: the runnable ideas of the 2026-11-14 idea slate, and a sequential Bayesian model

Four lanes. Each lane reads this brief, then its own section in `LANES.md`.

## Objective

`outputs/research/2026-11-14-idea-slate/IDEAS.md` lists fifty ideas. Twenty-two can be tested on
data already on disk; five are builds. This programme runs them:

- phase 1 corrects the valuation every later number is read against (lane L1);
- phase 2 tests execution and cost levers (L2) and selection and other-market ideas (L3);
- L4 builds a sequential Bayesian model that updates after each trade settles, with a card for
  every trade.

A lane succeeds if every idea it owns ends with a real-data number at the touch, with its N, its
interval and its basis, or with a precise statement of why it could not be run.

## Read before anything else

- `CLAUDE.md` and `CLAUDE.local.md` (rules, landmines), then `docs/RESEARCH_STATE.md` sections 2
  and 3. Name the nearest closed study for each idea and say how the test differs.
- `outputs/research/2026-11-14-idea-slate/IDEAS.md`: your ideas' rows.
- `outputs/research/2026-11-14-earnings-adjacent-hunt/BRIEF.md`: its "Rules this hunt adds"
  (1 to 6) apply here unchanged.
- `outputs/research/2026-11-13-niche-hunt/BRIEF.md`: its Standard and Hard limits apply here
  unchanged, with this folder and trial block substituted.
- `outputs/research/2026-11-14-earnings-adjacent-hunt/SUMMARY.md`: "Defects found" and "Review
  corrections". Every mistake listed there is a failure here.
- `earnings_iv_crush/research/protocol.py`, `earnings_iv_crush/research/hedged_hold.py`,
  `earnings_iv_crush/config.py` (`HEDGED_NET` is the settlement convention), and
  `earnings_iv_crush/engine/pnl.py::build_trade`. Any new P&L path reconciles to `build_trade` on
  shared events before it is trusted.

## Known data facts (from exploration; verify before building on them)

- **Base event panel.** `outputs/research/2026-11-02-parity-leg-choice/events.parquet` holds
  9,350 events, 2013-04 to 2026-08:
  - 7,753 are CRSP-hedged (2013-24) and 1,597 Yahoo-hedged (2025-26, with an assumed 3 bp equity
    half-spread);
  - the strike is the strike nearest the 15:59 parity forward;
  - features join one-to-one on ticker and entry_date from
    `outputs/research/2026-11-13-alpha-hunt-2/laneE-walk-forward-model/panel.parquet`, which has
    31 features stamped 15:59.
- **Hold paths.**
  - `research/timing/2026-11-02-hedged-event-hold/study.py::build_event`, with CRSP paths in
    `outputs/research/2026-10-20-hedged-hold/crsp_paths.parquet` (332 permnos, 2011-2024: prc,
    ret, cfacpr, closing bid and ask);
  - hedging starts at the reaction-session close;
  - sigma is one constant per hold;
  - median hold is 3 sessions.
- **Chains.** `data/cache/backfill_chains/` holds 27,353 full 15:59 parent chains, all expiries,
  with `bid_sz_00` and `ask_sz_00`. `data/cache/entry_1545_chains/` and `data/cache/flow/*` carry
  sizes too.
- **Rates.** FRED DFF and DGS2, 2011-2026, are in
  `outputs/research/2026-11-13-alpha-hunt/lane1-macro/dl/`.
- **Dividends.**
  - 2013-24: inferred from CRSP total against price return, as in
    `outputs/research/2026-11-14-earnings-adjacent-hunt/E4-expiry-mechanics/exdiv_audit.py`;
  - 2025-26: `outputs/research/parity_spread/dividends.parquet`, 1,601 rows.
- **Strike-centring defect.** It reaches:
  - `outputs/research/oos_2026_ledger.csv`;
  - the 53aa4898 panel `outputs/research/2026-11-02-maker-entry-hedged-hold/events.parquet`,
    whose strike is overwritten from that ledger;
  - lane 4's broad 2025-26 tick contracts;
  - E1 and E2.

  The hedged-hold 2025-26 confirmation panel is not affected.
- **Unnetted valuations.** Trials 1,819 (`laneB-contract-choice/score.py`) and 1,826
  (`hedged_short_strangle` in `research/execution/2026-11-02-smile-strike-hedged-hold/study.py`)
  are not netted.
- **No settled paper trades** exist on this machine.

## Rules for this programme

1. **Shared files.**
   - `earnings_iv_crush/config.py` and `earnings_iv_crush/research/hedged_hold.py` are edited
     with the Edit tool only, never rewritten whole, because two lanes may touch `config.py`.
   - Additions are backward-compatible: every existing default and result stays unchanged, and
     a test proves it.
2. **Records.** Never edit:
   - `oos_2026_ledger.csv`;
   - forward stores, closed study modules under `research/<line>/`, or anything under
     `research/*/preregs/`;
   - the project ledgers in `research/ledger/` (the team lead appends at the end).

   Corrections write new dated files in your lane folder.
3. **Hard limits.**
   - No metered pulls and no vendor API calls; the order path is not imported.
   - `.env` is never read, and EDGAR is never fetched.
   - Free web data only where robots.txt and the terms allow, with User-Agent `research-client`.
   - No licensed vendor rows in any markdown, figure or message.
4. **Code standard.** `from __future__ import annotations`, full type hints, NumPy docstrings, no
   magic numbers outside `config.py`. Run `python -m black` and `python -m ruff` at line length
   100. `python -m mypy earnings_iv_crush` must be clean. New tests go in `tests/research/` and run
   offline on synthetic data. Set `PYTHONIOENCODING=utf-8`.
5. **Blocks.**
   - Discovery is 2013-18 and held-out 2019-24.
   - 2025-26 is read only on the corrected panel, and only where `block_is_clean` passes.
   - List every view in your `blocks_viewed.csv` (columns as `log_block_view`).
   - 2019-24 is already viewed for most outcome families; say so and label the read exploratory.

## Deliverables

In `outputs/research/2026-11-14-slate-tests/<lane>/`:

- `evidence.md`, the dossier, organised by idea ID;
- `trials.csv` (trial_id, idea, rule, block, N, statistic, interval, verdict);
- `diagnosis.log`;
- freeze notes that hash themselves and the held-out scorer, with the scorer written first;
- `blocks_viewed.csv`, scripts and logs.

No `report.md` or `findings.md`. Take trial numbers only from your block in
`RESERVED_TRIAL_IDS.md`. British spelling, no em dashes.

## Your final message

Under 700 words, verdict first, one line per idea: its result with N, interval and basis, or why
it was not run. Then the search count, the package changes made, the tests added and their
status, and what you could not verify.

## Resume and checkpoint rules (added 2026-11-15, overnight run)

The first run stopped when the session restarted, and lanes L2 to L4 left no results. From now on:

1. **STATE.md.** Every lane keeps `<lane>/STATE.md`, rewritten after each idea or iteration. It
   lists:
   - the items done, with the file that holds each result;
   - the item in progress, with the exact next command;
   - the items not started;
   - the trial numbers used so far.

   A relaunched agent reads `STATE.md` first, plus the lane's `diagnosis.log`. It resumes from
   there and never recomputes a held-out read that is already on disk.
2. **Long jobs.** Any job expected to run more than about ten minutes writes its output
   incrementally, or to a temporary file that is renamed on completion, so a half-written file
   is never mistaken for a result.
3. **Stop time.** Each lane has a hard stop in local time (EST), given in its launch message.
   Check `date` before starting each item. At the stop time, write `STATE.md`, then send the
   final message.
4. **Git.** No commits. The user manages git, and the working tree holds the user's uncommitted
   work.
5. **Insight over volume.** For each result, write in `evidence.md` one paragraph on what it
   says about the mechanism (which P&L component carries it), not only the number.
