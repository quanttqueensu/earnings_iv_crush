# Earnings-adjacent hunt: parallel sources of alpha around the earnings event

Five lanes, run in parallel. Each lane reads this brief, then its own section in `LANES.md`.

## Objective

The project's core trade (sell the ATM straddle at the 15:59 bid before an after-close report)
has a real, vega-carried premium that the spread eats. This hunt looks sideways from that trade
for a different source of return attached to the same events, or to the option market's own
calendar: the other side of the volatility (long gamma, scalped), the information in pre-event
option flow, spillover to names that are not reporting, and option-market mechanics around the
expiry and the ex-dividend date. A lane succeeds if it delivers a tested candidate with real-data
evidence at the touch, or a precise, sourced case for why its idea is or is not worth a forward
test or a metered pull, with the pull priced.

## Read before anything else

- `CLAUDE.md` and `CLAUDE.local.md` (rules, landmines), then `docs/RESEARCH_STATE.md` section 2
  (closed directions, including the two 2026-11-13 alpha hunts and the niche hunt). Name the
  nearest closed study and say exactly how your test differs. Do not re-run a closed test.
- `outputs/research/2026-11-13-niche-hunt/BRIEF.md`: its Standard and Hard limits sections apply
  here unchanged, with this brief's folder and trial block substituted.
- `outputs/research/2026-11-13-niche-hunt/SUMMARY.md`, "Corrections made in review" and "Process
  breaches": every one of those mistakes is a failure here.
- `earnings_iv_crush/research/protocol.py` (`date_clustered_ci`, `matched_random_null`,
  `block_is_clean`, `log_block_view`), `earnings_iv_crush/research/hedged_hold.py` and
  `earnings_iv_crush/config.py` (`HEDGED_NET` is the settlement convention for new work), and
  `earnings_iv_crush/engine/pnl.py::build_trade` (any new P&L path reconciles to it on shared
  events before it is trusted).

## Data

Check what exists before designing. Relevant caches under `data/cache/` (inventory by listing and
reading small headers; never print vendor rows):

- `flow/broad_2023_2024`, `flow/broad_2025_2026`, `flow/megacap_2023_2024`: per event,
  `<TICKER>_<DATE>_pre.parquet` (the session before the report) and `_exit.parquet` (the reaction
  session). Find their schema and the builder that wrote them under `scripts/build/` or
  `earnings_iv_crush/data/`.
- `backfill_chains`, `entry_1545_chains`, `postea_chain`, `postea_quotes`, `postea_spots`,
  `postea_spots_crsp`, `fills`, `fills_et`, `alpaca_legacy` (option bars, including 1-minute, for a
  subset of names), `index_chains` (SPY, QQQ, IWM at 15:59 and 10:00), `dolthub_*`.
- Event files: `outputs/research/2026-11-02-hedged-event-hold/` and the hedged-hold study's
  builder; the WRDS calendar and CRSP spot via `earnings_iv_crush/data/wrds_r2.py` (the R2 mirror,
  already used by the project; no new credentials).

Free web data only where robots.txt allows it. Yahoo's chart and query endpoints, Stooq and the
Nasdaq calendar API disallow automated clients: do not use them. Never call a vendor API.

## Rules this hunt adds, from the niche hunt's failures

1. **Declare the primary before computing it.** Write hypothesis, mechanism, primary statistic,
   control, pass rule and kill rule in `diagnosis.log` first. If the primary fails on discovery,
   the lane may iterate, but every variant is a trial and a later variant that passes on a
   different statistic is labelled a statistic switch, not a pass.
2. **Count the search.** Report how many configurations were scored before the frozen one, and
   give the frozen rule's discovery t beside that count.
3. **Check the held-out block is clean** with `block_is_clean` against
   `research/ledger/blocks.csv` before freezing, and say so in the freeze note. If it is not
   clean, the read is exploratory and the note says why.
4. **A substitute price must be audited for bias, not only correlation.** If a hedge or settle
   price is rebuilt from another source, report the mean signed gap by subgroup (ex-dividend
   windows, expiry weeks) as well as the correlation.
5. **At the touch, on the project's basis.** Single-name results are per trade on m0 (0.20 times
   forward plus the 15:59 bid) unless the lane states and justifies another basis. Stock legs pay
   the stock half-spread plus 1 bp; option legs pay the quoted touch plus USD 0.65 per contract.
6. **Selectors** are scored on residual value and against `matched_random_null`, with strictly
   causal features (strictly earlier events only).

## Deliverables

In `outputs/research/2026-11-14-earnings-adjacent-hunt/<lane>/`: `evidence.md` (the dossier),
`sources.csv` (claim, URL, source type, verified/recalled/conjecture), `trials.csv`,
`diagnosis.log`, freeze note(s) that hash themselves and the held-out scorer (scorer written
first), scripts and logs. No `report.md` or `findings.md`. Trial numbers only from your block in
`RESERVED_TRIAL_IDS.md`. British spelling, no em dashes.

## Your final message

Under 600 words, verdict first: the candidate, its best evidence with N, interval and basis, the
search count behind it, the closest prior work and closest closed study, what it would take to
trade it at IB on the existing harness, and the single next step. List what you could not verify.
