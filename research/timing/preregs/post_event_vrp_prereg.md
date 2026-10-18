# Pre-registration: post-announcement short straddle held to expiry

## Hypothesis

After an earnings announcement the event uncertainty has resolved, but single-name implied
volatility on the next listed expiries may still exceed the volatility the stock then realises,
the single-stock variance risk premium (Goyal and Saretto, JFE 2009; Cao and Han, JFE 2013 on
delta-hedged single-stock option returns). The earnings book failed net because a liquidity taker
pays the spread twice, and the exit spread (3.02% per side at the exit-day 15:59) is the larger
leg. A straddle sold at the exit-day 15:59 and held to expiry pays one entry half-spread and settles
at intrinsic, so it is a structurally different cost profile on data already on disk.

Counter-arguments: post-event realised volatility stays elevated after large surprises (volatility
clustering), which favours the buyer; the generic single-stock premium is small for large caps once
costs are paid; and a short straddle held for weeks carries market-wide volatility risk (the block
contains the April 2025 sell-off). Closest prior work and the difference: Goyal and Saretto sort
all stocks monthly on the realised-implied gap and trade at mid-month quotes; this test trades only
the post-announcement window, unconditionally, entering at the bid with no exit trade.

## Scope and data

- Events: `outputs/research/events_broad_oos_2025.parquet`, exact duplicate rows removed, events
  whose EDGAR reaction session falls on or before the entry date removed (as in P1).
- Entry chain: the 15:59 ET consolidated quotes on the event's `exit_date` session
  (`data/cache/backfill_chains/{ticker}_{exit_date}.parquet`).
- Expiry: the shortest listed expiry with 14 to 45 calendar days remaining at entry.
- Strike: the strike nearest the parity forward (median of K + C - P over the three strikes with
  smallest |C - P|, usable quotes under P1's rule), with both legs two-sided.
- Settlement: S_T = the unadjusted (split-adjusted, dividend-unadjusted) yfinance close on the last
  session on or before expiry.

## P&L and costs, per contract (100 shares)

    credit = (call bid + put bid) * 100
    settle = |S_T - K| * 100
    pnl    = credit - settle - 2 * 0.65 - 0.0005 * S_T * 100 * 1{S_T != K}

The commission is USD 0.65 per contract per leg at entry; the last term is a 5 bp cost of disposing
of the stock delivered by the in-the-money leg. Margin = 0.2 * S_entry * 100 + credit, where
S_entry is the parity forward discounted at zero rate (the ledger's Reg-T convention). Return on
margin (RoM) = pnl / margin. The mid arm replaces the bids with mids and is reported beside it as
gross.

## Primary hypothesis and decision rule

Pass requires the mean net RoM per trade > 0 with a 95% bootstrap interval above zero, clustered on
expiry date (positions sharing an expiry share the terminal market move), 5,000 draws, seed 0.
Per-trade Sharpe is reported with the deflated Sharpe ratio against 1,504 trials. This is an
unconditional book, so the bar is zero net, not a selector null.

## Mechanism check

For a pass, the mean of entry ATM implied volatility (mid, Black-76 on the parity forward, zero rate)
minus realised volatility over the holding period (close-to-close log returns from entry to S_T,
annualised with the square root of 252) must be positive with a clustered interval above zero, and
the per-trade P&L must rise with that gap (positive Spearman). A pass on P&L without the volatility
gap is reported as unexplained and does not pass.

## Secondary, descriptive only

The mid arm; RoM by month of entry; the worst ten trades and the largest month; results excluding
entries from 2025-03-15 to 2025-04-30 (reported only to show tail dependence, never as a rescue);
maximum concurrent positions; per-trade return on premium.

## What is not allowed

No change to the expiry window, strike rule, settlement source, costs, clustering or sample after
any outcome is seen. Amendments are dated, hashed and reported beside the original.
