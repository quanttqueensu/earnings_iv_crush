# Pre-registration: post-event option surface predicts the stock's next 20 sessions

Frozen before any outcome for the declared blocks is computed. Changes after an outcome is viewed
require a dated amendment with its own hash. Record: `outputs/research/prereg_2026-10-20-post-event-equity.json`.
Scorer: `research/selection/2026-10-20-post-event-equity/study.py`.

## Hypothesis

E1 (skew). After the announcement resolves, names whose 25-delta put implied volatility is high
relative to at-the-money underperform the market over the next 20 trading days, and names with
low skew outperform. Mechanism: informed demand for downside protection that survives the
announcement reflects negative information not yet in the price (Xing, Zhang and Zhao, JFQA
2010).

E2 (term slope). After the announcement, names whose implied term structure is still inverted
(near-dated implied volatility above the next) underperform names with an upward slope.
Mechanism: an inverted post-event structure signals unresolved uncertainty or distress that the
stock price absorbs slowly. The sign rationale is a conjecture, labelled as such.

The trade is in the stock, so the option spread that binds the event book does not apply.
Nearest closed work: P1 put skew to the stock reaction (pre-event skew, reaction-day outcome,
wrong sign) and the PEAD option conditioners (60-day holds on surprise measures). Closest
published: Xing, Zhang and Zhao (2010); An, Ang, Bali and Cakici (JF 2014).

## Data and blocks

Events `outputs/research/ml_zoo/events_full.parquet`; chains `data/cache/backfill_chains/` at the
exit (reaction) session's 15:59 ET; CRSP `dsf` for returns and closing quotes; daily market
return from the Fama-French factors in `outputs/research/panel_daily.parquet`
(mktrf + rf). Discovery 2013-2018, validation 2019-2024 (exit dates). Confirmation not run
(no free point-in-time quote source for 2025-26 equity costs with the same basis).

## Specification

- Expiry: the shortest with 14 to 45 days from the exit date (Es); forward F from the strike
  minimising |call mid - put mid|. ATM IV from the straddle mid at the strike nearest F.
- E1 signal: the implied vol of the put whose Black-Scholes delta (at its own implied vol) is
  nearest -0.25, minus ATM IV, both on Es.
- E2 signal: ATM IV on the shortest expiry at least 21 days after Es, minus ATM IV on Es.
- Entry at the exit-date CRSP close; hold 20 trading days; outcome the stock's compounded return
  minus the compounded market return over the same days.
- Cost: half the CRSP closing quoted spread, floored at 1 bp, at entry and exit (round trip).
- Deciles from all events with strictly earlier exit dates, pooled, minimum 300. E1: long the
  lowest-skew decile, short the highest. E2: long the highest-slope decile, short the lowest.
- Position return: signed market-adjusted return minus the round-trip cost.

## Primary statistic and inference

Mean net position return per position (net, per 20-day hold, not annualised), cluster bootstrap
on exit dates, 5,000 draws, seed 0; per-position Sharpe; DSR against 1,539 trials.

## Success criterion

Lower bound above zero in discovery and in validation.

## Kill criterion

Discovery lower bound at or below zero closes that signal; validation is then not run.

## Trial accounting

Two trials (E1, E2). Count after this date's seven declared trials: 1,539.
