# Pre-registration: replace the event straddle's buy-back with a stock hedge held to expiry

Frozen before any return, P&L or price path of this trade is computed. Record:
`outputs/research/prereg_2026-11-02-hedged-event-hold.json`. Scorer:
`research/timing/2026-11-02-hedged-event-hold/study.py`.

## Hypothesis

Selling the front at-the-money straddle at the 15:59 close before an announcement and, instead of
buying it back at the 15:59 close of the reaction session, delta-hedging it with stock from that close
and letting the options settle at intrinsic on expiry, earns more per trade than the next-session
buy-back, and earns a positive net return on its own.

## Mechanism, built from three measured facts

1. **The exit is where the money goes.** Measured per-side cost on the book is 1.2714% of premium at
   entry and 3.0182% at exit (`fills_rescore.csv`, 34,672 prints): the exit is about 70% of the
   round trip. Exit spreads widen after announcements because the market maker now holds inventory
   in options whose new level is uncertain, and the in-the-money leg after a large move carries the
   widest dollar spread. Every test in the record paid that exit.
2. **Saving the exit by holding naked does not work, for an identified reason.** The closed
   conditional hold (section 2.3; mean advantage +0.0018 of margin, CI [-0.0045, +0.0087], N=193)
   kept the in-the-money leg's full stock exposure through the days after the announcement. Prices
   continue in the direction of the surprise (Bernard and Thomas 1989), which is the direction that
   loses for the short in-the-money leg. A stock hedge removes exactly that exposure at a cost of a
   few basis points.
3. **After the announcement the options are still rich, but entering them costs a spread.** The
   closed post-event hedged holds (2026-10-20, 14-45 days) were positive at the mid (+0.42% of margin)
   and negative at the touch only because they paid a fresh option half-spread (4-6% of premium).
   de Silva, So and Smith (Review of Finance 2025) find options keep losing value for two weeks after
   high-expected-volatility announcements as retail holders close slowly. A position already open
   from the earnings trade collects that decay without a new option crossing.

The combination crosses an option spread once (entry), not twice, and replaces the exit with stock
trades and settlement at intrinsic, which carry no option spread at all.

## Closest prior work and closed studies, and the difference

Conditional hold to expiry (closed, unhedged, conditional on a p70/p75 implied-move cut); the
2026-10-20 hedged holds (closed, new positions in 20-45 and 14-45 day options); the post-announcement
straddle held to expiry (closed, a new position). Published work on delta-hedged option returns around
announcements (Dubinsky et al. 2019; de Silva, So and Smith 2025) measures returns at the mid on new
positions. None holds the already-open event straddle past the announcement with a stock hedge, and
none compares that with the buy-back at the measured touch.

## Data and blocks

- Events: `outputs/research/ml_zoo/events_full.parquet` (11,257 events, 2013-2026, megacap and broad).
- Front contract at entry: `outputs/research/2026-10-20-hedged-hold/features.parquet` (`front_*`:
  the first expiry on or after the reaction session, the strike nearest the parity forward, straddle
  bid, mid and ask from the entry 15:59 chain).
- Exit quotes for the same strike and expiry: the reaction session's 15:59 chain,
  `data/cache/backfill_chains/{ticker}_{exit_date}.parquet`, read raw: the last record per contract,
  a leg usable for a buy-back when its ask is positive (a zero bid does not drop it).
- Stock: `outputs/research/2026-10-20-hedged-hold/crsp_paths.parquet` (CRSP daily, as-traded close,
  total return, closing bid and ask, cumulative price factor), to 2024-12-31.
- Blocks: **discovery 2013-2018**, **validation 2019-2024**, by entry date. Events whose front expiry
  falls after 2024-12-31 cannot be settled on CRSP and are excluded (counted). No outcome of this trade
  (hedged, front contract, held from the reaction-session close) has been computed on any block.

## Specification

- Sale: both legs at the entry bids, `S0 = front_bid`. Mid credit `front_mid`. Margin denominator,
  common to both arms: `m0 = 0.20 x front_fwd + S0` (the book's Reg-T approximation). The hedge's own
  margin is reported separately and does not enter the primary statistic.
- **Arm B (baseline, the existing book on the same contract):** buy both legs back at their 15:59
  asks on the reaction session. Commission USD 0.65 per contract per leg per side (four charges).
  `B = (S0 - exit_ask - 4 x 0.0065) / m0`.
- **Arm H (hedged hold):** no option trade at the reaction session. Hedging closes are the reaction
  session's CRSP close and every following session's close strictly before the front expiry. At each
  hedging close the position holds `+delta` shares against the straddle's `-delta`, Black-Scholes
  straddle delta at that close's spot, the strike, the years to expiry (ACT/365) and a hedge
  volatility fixed at the reaction session: the implied volatility of the same strike and expiry from
  the reaction session's chain mid when both legs are two-sided, else the 14-45 day post-event ATM
  implied volatility (`s2_iv`); an event with neither is dropped (counted). Each change in the hedge
  pays the CRSP closing half-spread, floored at 1 bp; the hedge is unwound at the expiry close. The
  options settle at intrinsic on the CRSP close of the expiry date, with 5 bp disposal of delivered
  stock when in the money. Commission: two option charges at entry only.
  Computed with `earnings_iv_crush.research.hedged_hold.hedged_short_straddle` (hedge starts at the
  reaction-session close; the move from entry to that close is unhedged in both arms). When the
  expiry is the reaction session itself, H settles at intrinsic on that close with no hedge.
  `H = net_pnl / m0`.
- Exclusions, each counted in the funnel: no front quote at entry; no reaction-session chain; either
  leg with no positive ask at exit (B undefined; H is still computed and its own book reported with
  and without these events); no CRSP permno or a missing close on any hedging or settlement date; a
  change in the CRSP price factor between the reaction session and expiry (split); expiry after
  2024-12-31. Dropped events are compared with kept ones on the absolute reaction-session move.

## Primary statistics and inference

- **P1, the exit lever:** mean paired difference `H - B` per event, unit `m0`; date-clustered 95%
  interval (`protocol.date_clustered_ci`, 5,000 draws, seed 0, clusters on the reaction session).
- **P2, the book:** per-trade Sharpe of `H` (net, on `m0`) with its date-clustered 95% interval, and
  mean `H`.

## Success criterion

PASS requires all three: (a) P1 mean > 0 with the interval excluding zero in discovery; (b) the same
in validation; (c) P2 per-trade Sharpe > 0 with the interval excluding zero in validation, and its
point estimate > 0 in discovery. (a) and (b) without (c) is recorded as "exit lever only": the hedge
beats the buy-back but the book still loses.

## Kill criterion

P1 mean <= 0 or its interval including zero in discovery closes the idea. A validation failure after
a discovery pass is recorded as "in-sample only".

## Secondary, descriptive only (cannot rescue a failed primary)

By days from the reaction session to expiry (0, 1-4, 5 or more); by universe (megacap, broad); a one-
shot hedge (hedge set at the reaction-session close and never rebalanced); the unhedged hold (the
closed 2.3 analogue, unconditional, front contract); at the mid; worst five events, skewness, and the
share of P&L from the worst 1% of events; the decomposition of `H - B` into exit cost saved, post-
reaction option P&L and equity cost; the hedge's peak notional relative to `m0`; deflated Sharpe ratio
against the trial count below. B is reconciled against the ledger's own next-session return
(`events_full.rom`) on events where both exist, and the correlation is reported.

## Trial accounting

One trial (the H-versus-B family with its standalone requirement). Count after this study: 1,549 + 1
= 1,550, the base inheriting the disagreement in `docs/RESEARCH_STATE.md` section 1.
