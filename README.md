# Earnings IV Crush

[![CI](https://github.com/jordanodorico/earnings_iv_crush/actions/workflows/ci.yml/badge.svg)](https://github.com/jordanodorico/earnings_iv_crush/actions/workflows/ci.yml)

**A quote-marked test of whether the volatility premium around scheduled
earnings announcements can be harvested, and the event-study and
execution-measurement engine built to settle it.**

Two findings, pulling in opposite directions.

**The premium is real.** Implied volatility falls on 98.1% of 989 events by a
mean of 48.65 volatility points, and profit attribution puts vega as the
largest positive leg under both path orderings, so the position earns through
the mechanism the thesis names. On a clean 2025-26 block that no configuration
was ever fitted to, the unconditional short straddle returns **+3.44% gross and
+0.49% net on margin across 1,221 events at a 61.0% hit rate**.

**The selector built to pick the best events is not.** On that same block the
frozen term-structure gate returns **-3.12%**, with a date-clustered 95%
interval of [-0.347, -0.058] excluding zero on the wrong side, and it loses to
picking events at random at a matched trade count. Its gross return is +0.07%,
so cost does not explain it: the gate finds events where the market charges a
large implied move, and those turn out to be the events where the large move
happens. It selects risk magnitude, not mispricing.

All Sharpe figures in this repository are per-trade unless a factor is stated.
The book trades roughly 35 times a year, so the defensible annualisation factor
is √35.2 ≈ 5.93, not √252 ≈ 15.87. An earlier version of this project made
exactly that error and the correction is documented rather than hidden.

**Setup:** `pip install -e ".[dev]"` (Python 3.10+), then `python -m pytest -q`.
The suite runs on synthetic fixtures and needs no network and no paid
credentials.

## Documents

- [`STRATEGY.md`](STRATEGY.md), the model: why the trade should work, the exact
  rules, the data and execution assumptions behind every number, results,
  limits, and what is still open.
- [`SUMMER_SUMMARY.md`](SUMMER_SUMMARY.md), the research record: every design
  tested and why it was kept or killed, a dated timeline, and what went wrong
  along the way.
- [`HIRING.md`](HIRING.md), the roles open on this project.

## Entry points

- `python scripts/validate_screen.py`, rebuilds the settled verdict from cached
  marks and checks it reproduces N = 391, Sharpe +0.055992 and the interval
  [-0.0421, +0.1803]. Costs nothing; the fastest way to confirm the machinery.
- `python scripts/run_research.py --real`, the main research run.
- `python scripts/agent_comparison.py`, fifteen selectors scored on one basis.
- `.github/workflows/paper_radar.yml`, a scheduled job that snapshots option
  chains after every close and commits its own book back to this repository as
  `paper-radar[bot]`, so the forward record is timestamped by a third party and
  cannot be back-dated.

Credentials live only in a git-ignored `.env`; `.env.example` lists the
variable names with no values.
