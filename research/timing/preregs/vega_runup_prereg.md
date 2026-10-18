# Pre-registration: pre-announcement vega run-up (state of record section 2.5)

## Hypothesis

Implied volatility of the front expiry rises into an earnings announcement (Patell and Wolfson 1979,
1981; Dubinsky, Johannes, Kaeck and Seeger RFS 2019). Gao, Xing and Zhang (JFQA 2018) report that
at-the-money straddles bought three days before announcements earn significantly positive returns
(1996-2013), concentrated in small, volatile, illiquid firms. If buyers underestimate announcement
uncertainty until the last days, a long straddle held from D-5 to the session before the print
(no gap risk is held) earns the run-up. The counter-argument, recorded in the handbook: with a
fixed expiry the event variance is already in the price at D-5, and the rising front IV is mostly
that fixed variance divided by a shrinking tenor, which the straddle price does not gain from;
theta on the diffusive part works against the holder. The test settles which reading holds net of
the touch.

Closest prior work and the difference: Gao, Xing and Zhang hold to the announcement date (which
includes the news for pre-open reporters) and use OptionMetrics closing mids; this test exits
before any news, on S&P 500 names, 2019-2024 (after their sample), priced at the touch.

## Scope and data

- Events: `outputs/research/dolthub_sp500_events.parquet`, all 1,421 events (64 tickers A to CHD,
  2019-02 to 2024-11; the alphabetical truncation is a build artefact unrelated to outcomes).
- Chains: DoltHub `dolthub/options` end-of-day snapshots. Entry session E5 = the fifth trading
  session before the event's `entry_date` (D-1, the last session before the reaction); exit at the
  `entry_date` snapshot. Sessions are counted on the source's own trading dates (lookback 0; a
  missing snapshot steps the count to the next earlier session that exists, at most 3 extra).
- Matched null: for each event, the identical trade on the same ticker in a window shifted 30
  trading days after the event's `exit_date` (pseudo D-1 = exit_date + 30 sessions on the business
  day calendar; pseudo E5 five sessions earlier), dropped if any event of that ticker falls within
  10 business days of the window.

## Trade construction

- Expiry: the shortest listed expiry strictly after the event's `exit_date` (the null uses the
  shortest expiry strictly after pseudo D-1 + 1 business day). Strike: minimises |call mid - put
  mid| at entry among strikes with both legs two-sided. The same contracts are priced at exit.
- Quotes usable when 0 < bid <= ask. Long return at the touch per unit of entry mid premium:
  (call bid + put bid at exit - call ask - put ask at entry) / P0. Mid arm reported beside it.
- Funnel printed at each drop (missing chain, no expiry, no strike pair, leg missing at exit).

## Primary hypothesis and decision rule

Pass requires both, 95% intervals, date-clustered bootstrap on `entry_date` (5,000 draws, seed 0):
(i) mean long touch return per trade > 0 with the interval above zero; and
(ii) mean paired difference (event minus its matched null window, events with a valid null only)
> 0 with the interval above zero.
Per-trade Sharpe with the deflated Sharpe ratio against 1,497 prior trials plus the four declared
in this session (two SPY families, this test, and the PEAD freeze if declared).

## Secondary, descriptive only

The D-3 entry variant (Gao, Xing and Zhang's window); the mid arm; decomposition of the mid P&L
into the front IV change times vega and the residual (theta and gamma) using the source's IVs;
splits by entry half-spread tercile and by year. None can rescue a failed primary.

## What is not allowed

No change to the window, expiry rule, strike rule, null construction or cost basis after prices are
seen. Amendments are dated, hashed and reported beside the original.
