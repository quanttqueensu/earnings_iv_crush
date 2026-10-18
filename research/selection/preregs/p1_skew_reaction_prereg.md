# Pre-registration: P1, pre-announcement put skew predicts the earnings-window stock return

Frozen before any stock or index price for the 2025-2026 block is loaded and before any skew
value is related to a return. Changes after an outcome is viewed require a dated amendment.
SHA-256 recorded in `outputs/research/prereg_p1_skew_reaction.json`. Scorer:
`scripts/research_p1_skew_reaction.py`.

## Hypothesis

Traders with adverse private information about an upcoming earnings release buy out-of-the-money
puts, the cheapest levered way to express a negative view. Their demand steepens the put side of
the smile relative to the at-the-money level before the announcement, so a steep pre-announcement
put skew predicts a negative market-adjusted stock return over the announcement window. This
test trades the stock, not the option: the option surface is the signal only.

**Mechanism check.** The relation must run through the announcement. Reported beside the primary
statistic, never used to rescue it: the same top-minus-bottom gap over a placebo window that ends
before the release (close of entry day minus 3 sessions to close of entry day) should be smaller
in magnitude than the announcement-window gap. A pass whose placebo gap is as large as its
announcement gap is reported as unexplained (a persistent skew-return effect, not
announcement-specific informed trading).

## Prior work and how this differs

Xing, Zhang and Zhao (JFQA 2010) sort stocks weekly on the smirk (OTM put IV minus ATM call IV
from OptionMetrics end-of-day surfaces) and find the steepest-smirk quintile underperforms the
flattest by about 10.9% a year, with predictability that includes earnings surprises. Jin, Livnat
and Zhang (JAR 2012) show that skew and the call-put IV spread measured before earnings and other
corporate news predict the announcement return, consistent with option traders holding an
information advantage. Cremers and Weinbaum (JFQA 2010) document the IV-spread analogue, and
Atilgan (JBF 2014) the earnings-window version. The direction is published and crowded; post-
publication decay of anomalies averages roughly half (McLean and Pontiff, JF 2016). (Citations
and magnitudes are recalled from the papers, not re-verified for this document.)

This version differs in four ways: (1) the skew is read from a consolidated-quote 15:59 ET snapshot
on the entry session, on the front expiry that spans the event, at an interpolated 25-delta strike
in forward-delta space, rather than an end-of-day standardised surface; (2) the outcome starts at
the entry close, which precedes the release, with release timing checked against SEC EDGAR 8-K
acceptance times; (3) the sample is a single untouched block (2025-01 to 2026-06), after
publication, scored once; (4) the statistic is net of a stated cost.

## Scope and data

- **Events.** `outputs/research/events_broad_oos_2025.parquet`: the 2,037 session-aware events of
  the 2025-2026 broad block (346 names). Only `ticker`, `announce_date`, `entry_date` and
  `exit_date` are read; no price, realised move or P&L column is used.
- **Session.** From the calendar (`events_master_broad.parquet`) as already encoded in
  `entry_date`: BMO entries are the prior session's close, AMC entries the announcement-day close.
- **Chains.** `data/cache/backfill_chains/{ticker}_{entry_date}.parquet`, the 15:59 ET
  consolidated quote snapshot on the entry session, parsed with
  `scripts.backfill_forward_window._parse_chain` (last quote per contract, bid and ask both
  positive).
- **Prices.** Daily adjusted closes (dividends and splits) for each name and SPY from yfinance,
  pulled once after this file is hashed. CRSP on the R2 mirror ends 2024-12 and does not cover the
  block.

## Signal construction

1. **Expiry.** `earnings_iv_crush.data.features.select_execution_expiry(chain, announce_date,
   exit_date, min_dte_days=STRATEGY.min_exit_dte_days)` (= 2): the first listed expiry after the
   announcement with at least two weekdays of life after the exit session. This is the expiry the
   straddle book trades; it spans the event and avoids one-day options whose wing IVs are unstable.
2. **Time to expiry.** `T = (expiry - entry_date).days / 365` (ACT/365, close to close).
3. **Quote filter.** A contract is usable when `bid > 0`, `ask > bid` and the relative spread
   `(ask - bid) / mid <= 0.50`. Unusable contracts are removed before any bracketing.
4. **Forward.** Over strikes where both call and put are usable, take the three strikes with the
   smallest `|C_mid - P_mid|` and set `F = median(K + C_mid - P_mid)` (put-call parity with zero
   rate, `GlobalConfig` risk-free 0.0; the discount over at most about five weeks is negligible).
   Using the parity forward absorbs dividends and borrow without a spot price.
5. **Implied volatility.** Black-76 on the mid with forward `F`, zero rate:
   `earnings_iv_crush.engine.greeks.implied_vol(mid, F, K, T, 0.0, right, hi=10.0)`. A contract
   whose mid cannot be inverted (below intrinsic, outside the bracket) is removed. European
   inversion of American single-name options: early-exercise value on short-dated OTM puts is
   small and affects both legs of the difference in the same direction.
6. **ATM call IV.** Usable calls with inverted IV; take the two listed strikes bracketing `F`
   (`K_lo <= F < K_hi`) and interpolate IV linearly in strike to `K = F`. If `F` equals a listed
   strike that strike's IV is used. No bracket: event excluded.
7. **25-delta put IV.** Usable puts with `K <= F` and inverted IV. Each put's forward delta
   magnitude `N(-d1)`, `d1 = (ln(F/K) + 0.5 sigma^2 T) / (sigma sqrt(T))`, uses its own IV. Scanning
   from the strike nearest `F` outward, take the first adjacent pair whose delta magnitudes
   bracket 0.25 and interpolate IV linearly in delta magnitude to 0.25. No extrapolation: if the
   usable strikes never reach 0.25, the event is excluded.
8. **Signal.** `skew = IV_put25 - IV_atm_call` in decimal volatility. Higher means steeper put skew.
   The raw difference is used, as in the prior work, not scaled by the ATM level.

## Exclusions (applied in this order, each printed in the funnel)

1. No entry chain on disk.
2. No qualifying expiry.
3. Forward, ATM call IV or 25-delta put IV cannot be formed under the rules above.
4. **Release before the snapshot.** The EDGAR checker (`earnings_iv_crush/data/edgar_sessions.py`,
   output `outputs/research/edgar_sessions/agreement.csv`) gives each matched event a reaction
   session (first session whose open follows the 8-K). An event whose EDGAR reaction session is on
   or before the entry date is excluded: the 15:59 snapshot would already reflect the release.
   Events without an EDGAR match are kept on the calendar's timing.
5. No adjusted close for the name or SPY on the entry date or on the second session after it.
6. Calendar-month buckets (below) with fewer than 50 events are merged, not dropped.

## Outcome

`r_i = (P_{t+2} / P_t - 1) - (SPY_{t+2} / SPY_t - 1)`, adjusted closes, `t` the entry session and
`t+2` the second NYSE session after it (sessions taken from SPY's own price index).

The window works for both sessions without using the session label: a BMO event enters at the
close before the announcement morning, so `t+1` is the first reaction session; an AMC event enters
at the announcement-day close, so `t+1` is again the first reaction session. `t+2` adds one session
of continuation in both cases and absorbs a calendar date that is one session late (the EDGAR
"later" case). The only timing error that contaminates the signal is a release before the 15:59
snapshot, which exclusion 4 removes where EDGAR can see it.

Per-event market adjustment uses a beta of one, a per-trade basis, not annualised.

## Deciles

Assigned **within calendar-month buckets** of the entry date, not pooled. The market-wide level of
put skew moves with regime (the April 2025 tariff shock lifted every name's skew together), and the
index return over the same days co-moves with that level. A pooled sort would load the extreme
deciles on calendar time, turning the top-minus-bottom gap into a market-timing bet that the
market adjustment only partly removes, and would let a few dates dominate the clustered bootstrap.
Within-month sorting compares names facing the same market. Buckets: calendar months in order; a
month with fewer than 50 eligible events is merged forward into the next month until the bucket
holds at least 50; a short final bucket merges backward into the previous one. Within each bucket,
events are sorted by skew ascending (ties by ticker) and decile `d = floor(10 (rank - 1) / n) + 1`.
Decile 1 is the flattest skew, decile 10 the steepest.

## Primary statistic and inference

- **Gap.** `G = mean(r | decile 1) - mean(r | decile 10)`: long the flattest-skew decile, short the
  steepest, market-adjusted, per event, gross.
- **Costs.** 5 bp per side on the stock. Each leg is a round trip (two sides), and the long-short
  holds two legs, so `G_net = G - 0.0020`. The SPY hedge nets across the two legs under beta one
  and is not charged separately.
- **Interval.** Date-clustered percentile bootstrap on `G` with clusters = entry date, 5,000 draws,
  seed 0 (`earnings_iv_crush.engine.event_study.cluster_bootstrap_ci`); the net interval is the
  gross interval shifted by 0.0020.
- **Monotonicity.** Spearman correlation between decile number (1 to 10) and decile mean gross
  return. The hypothesis predicts a negative value.
- **Matched random null.** 1,000 draws, seed 0: within each bucket, the skew values are permuted
  across events, deciles reassigned and `G` recomputed. This preserves bucket composition, decile
  sizes and the date structure exactly. Reported: the null median, 95th percentile and the
  observed gap's percentile.
- **Deflation.** The long-short book as a per-event series: `+r_i - 0.0010` for decile-1 events and
  `-r_i - 0.0010` for decile-10 events (each event a round trip at 5 bp per side). Per-trade Sharpe
  with date-clustered CI, and the deflated Sharpe ratio against 1,498 trials (1,497 recorded before
  this one) with the trial-Sharpe dispersion in `outputs/research/performance_panel.csv`. That
  dispersion comes from straddle trials, a different return type; the DSR is a guide, not a gate.
- **Power, stated before the result.** With about 1,800 scored events, deciles of about 180 and an
  announcement-window market-adjusted return dispersion of roughly 7%, the standard error of `G` is
  about 0.7 points before clustering, so the minimum detectable gap at conventional power is about
  2 points per event. Smaller true effects will not be found in one block.

## Kill rule and success criterion

**Kill** if either: (a) no monotone ordering, defined as Spearman(decile, decile mean) above
-0.60; or (b) the 95% interval on `G_net` includes zero.

**Pass** requires all of: Spearman at or below -0.60; the `G_net` interval excludes zero and is
positive; and the observed gross `G` at or above the 95th percentile of the matched null. A kill on
(a) or (b), or a gap inside the null's 95th percentile, is a fail.

## Secondary, descriptive only (cannot rescue a fail)

Pooled deciles; the EDGAR-matched subset only; BMO and AMC separately; the `[0, +1]` window; the
placebo window of the mechanism check; decile 1 and decile 10 legs separately.

## Exposure before freezing

Before this file was written: three rows of the event file and three rows of the 2025-26 straddle
ledger were printed during a schema inspection (they show entry and exit spot and straddle P&L for
those events); fifteen entry chains were parsed to check that the 25-delta construction is
feasible, with no price or return loaded. No skew value has been related to any return on this
block. The block's outcomes were viewed once before, for the term gate's straddle P&L only. The
programme's earlier skew gates (state of record, appendix A) were selectors for straddle P&L, a
different outcome; this is the first directional stock-return test on skew in the programme.

## Second block

The DoltHub 2019-2024 chain is the planned second block. It lists only about three expiries
(nearest a median of 16 days out) and serves end-of-day marks, so its signal would be a different
construction. It is not part of this test and would need its own pre-registration.

## Common

One trial. DSR against 1,498. Per-trade figures; nothing annualised.
