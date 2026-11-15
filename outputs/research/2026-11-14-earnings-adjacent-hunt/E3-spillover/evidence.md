# E3 spillover: evidence dossier

## Hypothesis, scope and success criteria

When a company reports, its same-industry peers that are not reporting may be mispriced in two
ways. Their options may not price the night as an event (buy peer variance), or their stock may
under-react to the reporter's news and drift the next session (trade the peer's stock in the
direction of the reporter's reaction). Scope: the project's 332-permno event universe, reporters
and peers both drawn from it, 2013-2024, peers defined by three-digit CRSP SIC on the reporter's
entry date, a peer excluded if it has any known report from two sessions before the reporter's
entry to two sessions after its reaction (six for the five-session trial). Discovery 2013-2018,
held-out 2019-2024 (CRSP in the mirror ends 2024-12-31). Success: a frozen rule whose held-out
mean is positive net at the touch with a date-clustered 95% interval excluding zero, and above
the 97.5th percentile of a date-level random-direction null. Declarations are in `diagnosis.log`
entry 2, written before any return was computed.

## How this differs from the closed studies

- Section 2.1 peer-informed selection (`research/selection/findings/section21_peer.md`) and lane5
  "early in industry" (alpha hunt 1) are selectors for which reporter's straddle to sell. Here the
  traded name is the non-reporter.
- Earnings covariance (`season_state_and_earnings_covariance.md`) weights reporters by covariance
  as a selector; no peer is traded.
- Alpha hunt 2 lane G traded QQQ options on mega-cap nights (priced fairly). Here the instrument is
  the single-name peer, and the variance test asks whether the peer's own night is an event.
- Buying peer variance and the peer directional trade differ in what they need: the first needs
  extra second-moment movement on the night that the peer's options did not price, the second
  needs first-moment information that the peer's stock has not absorbed by the reaction close.
  The variance test is decided by realised variance alone (an upper bound on the buyer's take);
  the directional test needs only closes and closing quotes.

## Data feasibility

Of 20,855 peer nights, a touch-quality chain (Databento cbbo-1m at 15:59) exists for the peer on
both the reporter's entry and reaction sessions on **zero**: the Databento caches hold chains only
on each name's own event sessions. DoltHub exact-date files exist by name for 56 (runup) and 95
(p2) peer nights, but every one is an empty sentinel. Alpaca's panel covers 1,059 peer nights in
2024, but carries last-trade closes stamped on both sides, not quotes. `index_chains` covers SPY,
QQQ and IWM only; no sector ETF chains are cached. The option test at the touch is therefore
infeasible at zero cost, and was reduced to a realised-variance ceiling plus a priced pull.

An exclusion leak was found and fixed before freezing: names outside the panel calendar and the
Compustat link (EQR, KIM, CPT and others) were counted as non-reporting on their own report
nights. The broad calendar the 15:59 history was pulled from and every backfill chain day were
added to the exclusion; peer nights fell by 3.6% and every declared trial was re-scored
(`diagnosis.log` entry 4; the leaky outputs are in `superseded/` and are not cited).

## Results

Real data, CRSP daily returns and closing quotes. Per trade, basis points of peer notional, net
at the touch (peer closing half-spread plus 1 bp per side, SPY hedge 1.3 bp per side), date-
clustered 95% intervals on the reaction date.

| Trial | Rule | Block | N (dates) | Gross | Net |
|---|---|---|---|---|---|
| 2742 | continuation, next session (primary, frozen) | 2013-18 | 4,803 (481) | +3.33 [-2.38, +8.90] | -4.51 [-10.20, +1.07] |
| 2742 | same, held-out read once | 2019-24 | 9,779 (678) | -1.50 [-6.98, +3.85] | -9.94 [-15.48, -4.54] |
| 2743 | reversal, next session | 2013-18 | 4,803 (481) | -3.33 | -11.17 [-16.77, -5.39] |
| 2744 | lead reporters only | 2013-18 | 1,833 (335) | +0.04 | -7.67 [-16.20, +1.02] |
| 2745 | five-session hold | 2013-18 | 4,111 (453) | -2.34 | -10.01 [-22.74, +2.70] |
| 2746 | Thomas-Zhang reversal to the peer's own report | 2013-18 | 2,099 (420) | +1.43 | -6.63 [-46.82, +34.83] |
| 2750 | reactions of 3% or more | 2013-18 | 2,915 (373) | +4.60 | -3.45 [-9.99, +3.33] |
| 2751 | magnitude-weighted | 2013-18 | 4,803 (481) | +1.68 | -6.21 [-13.00, +0.28] |
| 2752 | laggard peers | 2013-18 | 1,952 (394) | +6.25 [-1.18, +13.83] | -1.80 [-9.05, +5.70] |

The held-out per-trade Sharpe of 2742 is -0.057 [-0.089, -0.026] net; the sign-flip null puts its
gross mean at the 29th percentile. Ten directional and variance configurations were scored before
the freeze (2742 to 2752, with 2748 unscored and 2753 withdrawn), and the best discovery gross
(2752, t about 1.7, sign-flip percentile 94.4) does not clear the random-direction null, before
any deflation for the search.

**Mechanism (right driver).** The transfer is real and fast. Signed by the reporter's abnormal
reaction, the peer's same-session hedged return is +26.9 bp [+21.1, +32.7] on discovery and
+38.1 bp [+32.1, +44.3] on held-out; the slope of the peer on the reporter's abnormal return is
0.046 and 0.059. It is complete by the reaction close: nothing continues or reverses the next
session, over five sessions, or into the peer's own report. This matches Frankel, Godigbe and
Rabier (2025), who find low co-movement on announcement days, and Chung, Hrazdil and Trottier
(2014), who find the Thomas-Zhang over-reaction gone in recent, higher-volume years.

**Option arm.** The ratio of the peer's squared return on the reporter's reaction session to its
ordinary sessions (trial 2749, control excluding the peer's own report windows) is 0.97
[0.88, 1.07] on discovery and 0.86 [0.74, 1.01] on held-out (market-adjusted 0.98 [0.89, 1.08]
and 0.96 [0.85, 1.10]), N=6,173 and 11,939 peer dates. A non-reporting peer's night is an
ordinary night. A one-night long front straddle bought at the 15:59 ask and sold at the next
15:59 bid would need a ratio of about 3.4 to 4.6 even if its options priced nothing extra
(gross take 0.5 x (VR - 1) / n of premium, n about 15 sessions to expiry, round-trip touch 8 to
12% of premium from the hedged-hold study's 4-6% half-spread). The upper bounds are below 1.1.
The first discovery read (2747, 0.81) used a control contaminated by the peer's post-report
sessions and is superseded. The seller's side was sized from Alpaca's last-trade panel (2754,
exploratory, 2024): the peer's front ATM implied vol falls by 0.39 vol points more on the
reporter's night than on its ordinary nights [-1.00, +0.11], N=666 on 95 dates, against the
2.4 to 3.6 points a one-night short needs to pay its touch. This is consistent in sign with
Hann, Kim and Zheng (2019) and an order of magnitude too small to trade.

## Pricing the option pull

The Databento OPRA cbbo-1m 15:59 history cost USD 20.87 for 7,773 events at two chains each,
about USD 0.0013 per ticker-session chain (derived from the logged spend, not a vendor cost
call). Peer nights need 33,670 unique chains for 2013-24 (about USD 45, or USD 90 with an equal
number of control nights), 21,962 for 2019-24 (about USD 29 or 59) and 8,264 for 2023-24 (about
USD 11 or 22). The builder's `--price-sample` is the authority before any spend. On the evidence
above the pull is not recommended: it would measure a quantity (the peer's one-night IV change)
whose crude estimate is about a third of the break-even at its 95% bound.

## Tradability at IB

The directional trade is a market-on-close order in the peer and an offsetting SPY order, held
one session. IB routes MOC equity orders on a paper account, but the project's harness
(`scripts/paper_trade_ibkr.py`) is options-only and would need an equity order path and a
same-day decision before the 15:50 MOC cut-off. The signal is idealised: the test uses the
reporter's closing return, while a live order would see the 15:45 return. That favours the
strategy and it still fails.

## Limitations

- Universe: peers are the 332 liquid optionable event names; small, neglected peers (where Hou
  2007 finds diffusion strongest) are outside it, as are customer-supplier links (Cohen and
  Frazzini 2008), which would need segment data not in the project.
- CRSP closing quotes are the cost basis; a closing-auction fill would pay less than the
  half-spread, but the gross is not distinguishable from zero, so no cost basis rescues it.
- The held-out block is clean on the ledger for these outcome families, but CRSP 2019-24 returns
  of these names have been used by other studies for other outcomes.
- Exploratory regime: unhashed by `protocol.freeze_prereg`; the freeze note hashes itself and the
  scorer, and `s06_heldout.py` refused to run without both matching.

## Files

All under `C:\Users\jodor\Documents\QUANTT_IVCrush_Project\outputs\research\2026-11-14-earnings-adjacent-hunt\E3-spillover\`:
`diagnosis.log`, `trials.csv`, `sources.csv`, `freeze_2026-11-14_spillover.md`, `lib.py`,
`spill.py`, `s01_peer_nights.py` to `s07_alpaca_peer_iv.py` with their logs, `peer_nights.parquet`,
`discovery_results.json`, `iterate_results.json`, `heldout_results.json`, `block_views.csv`,
`feasibility.json`, `alpaca_peer_iv.csv`, and `superseded/` (outputs of the leaky first pass).
