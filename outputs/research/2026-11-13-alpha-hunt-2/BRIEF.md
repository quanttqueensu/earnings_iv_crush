# Alpha hunt 2: shared brief for ten parallel research agents

Repo: `C:\Users\jodor\Documents\QUANTT_IVCrush_Project` (many uncommitted changes; leave every
existing file exactly as it is).

## The goal

Find a source of alpha in single-name event options that the project does not already have. The
owner wants persistence: when an idea comes back negative, do not stop. Diagnose why from the
individual events (which events drove the loss, what they share, whether the measurement or the
mechanism failed), write that diagnosis down, fix what you think went wrong, and test the fixed
version. Then keep generating and testing ideas. Each fix is a new hypothesis and a new logged
trial, never a quiet re-run.

Be energetic in the search and strict in the measurement. A wanted result never changes how
anything is measured.

## Where the project stands (design inputs)

Read `outputs/research/2026-11-13-alpha-hunt/SUMMARY.md` first; it is the result of round 1. The
essentials:

- The trade sells an ATM straddle the session before an earnings announcement. The crush is real
  (ATM IV falls on 98.1% of 989 events) and every book is positive gross at the mid. Every book is
  negative net at the touch. The edge is eaten by the spread paid, not by event choice.
- No selector has survived a held-out read: macro state, surface richness, own-history move,
  calendar and cross-sectional features, per-trade forensics, term structure, skew, VRP and more.
- The real levers are structural. A delta-hedged hold to expiry instead of the next-day buy-back
  adds +1.7 to +2.8% of margin per trade in every block (N 1,597 to 4,676), and selling at 15:45
  instead of 15:59 adds +0.5% on broad names. Even so, the hedged hold plus 15:45 entry loses about
  1% of margin per trade in 2013-19 and 2020-24. The one positive 2025-26 reading was
  attrition-biased.
- The base unit: m0 = 0.20 x forward + 15:59 bid premium. Per-event hold tables live in
  `outputs/research/2026-11-02-hedged-event-hold/` (columns B, H, naked and more; about 9,350
  events 2013-26 with status ok). Reusable per-event features from round 1:
  `outputs/research/2026-11-13-alpha-hunt/lane1-macro/panel.parquet`,
  `lane2-forensics/ledger_all.parquet`, `lane3-surface-flow/all_features.parquet`,
  `lane5-niche/features.parquet`, `lane4-structure/tick_panel.parquet`.

## Read before proposing anything

1. `docs/RESEARCH_STATE.md` (closed list and figures never to quote), `docs/PROTOCOL.md`,
   `research/ledger/blocks.csv` (which blocks are already viewed for which outcome).
2. The project `CLAUDE.md` and `CLAUDE.local.md`.
3. **Before calling any idea new, search `research/` and `outputs/research/` for a study folder
   on it** (Grep for the key words). Round 1 re-proposed a combination already scored as trial
   1,554. If it exists, read its findings and test only what differs, saying what differs.

## Method

- **Split before you look.** Choose a discovery block and a held-out block, and state both at the
  top of your trial log. Check `research/ledger/blocks.csv`: if no block is clean for your outcome
  and feature family, everything you report is exploratory; say so.
- **Every scored variant is a trial.** Append it to `trials.csv` in your folder as soon as it is
  scored, with these columns: trial id, hypothesis, mechanism (stated before scoring), block, N, effect,
  CI low, CI high, t, null percentile, basis, verdict. Use only your reserved trial numbers
  (`RESERVED_TRIAL_IDS.md`). Failures stay in the log.
- **Point in time.** Every feature must be computable before its decision time; state the
  timestamp. No revised series, no adjusted prices joined to raw strikes without the split factor.
- **Statistics.** Use `earnings_iv_crush/research/protocol.py`: `date_clustered_ci` for every
  interval, `matched_random_null` for every selector, against a tenor-matched null. For a change
  to the trade, use the paired difference against the base trade on the same events. Report the
  level of the book as well as any paired gain: a gain that leaves the book negative is cost
  recovery, not alpha. Before choosing a statistic, check that it can answer the question given the
  sign and scale of the outcome (no Sharpe comparisons on a negative-mean book).
- **Basis beside every number:** per trade, unit (m0 or premium), net or gross, touch or mid.
  Never annualise unless the factor comes from the book's own trade cadence.
- **Coverage and attrition.** Any join to cached ticks or chains can drop events in a way that
  depends on the outcome (round 1's tick pull followed a ledger that drops events with no exit
  bid; the dropped events lost about 5% of m0). For every join, print a funnel and compare the
  outcome of covered and uncovered events before reading a level.
- **Provenance.** A hypothesis formed by reversing a failed one, or read off discovery bins, is
  discovery-derived; label it so in its freeze note.
- **The iteration loop.** For each failure, write two or three lines in `diagnosis.log` (append):
  what the per-event evidence shows, what you think went wrong, what you will change. Then score
  the changed version as a new trial. Aim for at least three rounds and at least eight hypotheses.
  Take the best one or two, frozen in a dated `freeze_<slug>.md` note written before the read, to
  the held-out block once.
- **Labels.** Confirmatory only if frozen before a held-out read on a clean block, with t >= 3,
  null percentile >= 95, and a mechanism stated in advance. Everything else is exploratory or
  descriptive.

## Hard limits

- Zero spend. No Databento, WRDS or any other metered call. Free public data is allowed (FRED,
  yfinance, Cboe history, DoltHub) with a generic client name; never put the owner's name, email or
  project name in a request. No SEC EDGAR fetches.
- Write only inside your folder `outputs/research/2026-11-13-alpha-hunt-2/<your-lane>/`: scripts,
  logs, parquet, `trials.csv`, `diagnosis.log` and freeze notes. The harness refuses report files
  from subagents, so do not write `report.md`; your final report goes in your final message.
- No git commands that change state. No ssh, no VM, nothing under `deploy/`, nothing that touches
  the paper book or a broker.
- `data/processed` holds about 152,000 files: never list it, glob it broadly or run a recursive
  find over the repo.
- No further agents. No background jobs left running.
- Usage is tight and ten agents share it: prefer one script that scores several variants to many
  small runs, reuse stored features, and keep `trials.csv` current so nothing is lost if you are cut
  off.

## Final message

Verdict first (did anything survive a held-out read, and is any book net positive at the touch).
Then the top three results with N, effect, CI, null percentile, basis and label; the iteration
story (what failed, why, what you changed); failed ideas one line each; what you could not test;
and the absolute path of your folder.
