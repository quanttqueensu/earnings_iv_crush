# E2 informed flow: evidence dossier

## Hypothesis, scope and success criteria

Hypothesis: net buying of calls minus net buying of puts on the event's at-the-money pair in the
last hour before an after-close earnings release predicts the sign of the stock's move across the
release by enough to pay a stock round trip at the touch. Scope: a directional stock trade (cheap
touch), not a volatility trade, on the events the project already holds tick data for. Success:
a declared primary whose discovery interval (per position, net, date-clustered 95%) lies above
zero and beats both a random-direction and a matched null at the 95th percentile, then the same on
a held-out block read once. Declared in `diagnosis.log` entry 1 before any signal or outcome was
computed. All results are real data, exploratory under the hunt's rules.

## Data

- `data/cache/flow/*` are Databento OPRA `cmbp-1` records (quotes and trades) for exactly two
  instruments per event: the call and put of the sold straddle (front expiry, strike from the
  15:59 chain). Builders: `research/execution/research_flow_liquidity.py` (pre files from 09:30
  two business days before entry to 16:00 on entry day, and exit files 15:00 to 16:00 on the
  reaction session; broad 2025-26, 1,220 events; megacap 2023-24, 243) and
  `research/execution/2026-11-13-maker-entry-confirmation/study.py` (entry files 14:55 to 16:00,
  broad 2023-24, 1,712 events). Trades carry no aggressor flag (side N), so trades are signed by
  the quote rule against the prior two-sided mid of the same contract.
- What the files cannot support: no other strikes, no out-of-the-money puts, no open/close or
  customer flag, no stock volume. Pan and Poteshman's open-buy ratio, Johnson and So's O/S and
  OTM put buying are not buildable here. The signal is the public-tape analogue: quote-rule
  signed volume on the near-the-money pair.
- Outcome: the stock's 15:59-to-15:59 return from put-call parity forwards on one expiry for both
  sessions (`data/cache/backfill_chains`), so dividends net out; CRSP close-to-close for the 243
  megacap events (no cached chains); CRSP close-to-open for trial 2,713. CRSP on the R2 mirror ends
  2024-12-31, so the held-out block uses parity only.
- Audit of the substitute price (brief rule 4), broad 2023-24, N=1,707: correlation with CRSP
  0.9993; mean signed gap (parity minus CRSP) -2.88 bp [-4.34, -1.32]; ex-dividend inside the
  window N=5, -5.13 bp [-16.10, +5.41]; expiry within two days -3.73 bp against -2.07 bp
  otherwise; two events with |gap| above 1% (`audit_discovery.log`). No subgroup bias of a size
  that matters against a 5% one-night move.
- Cost per side: stock half-spread plus 1 bp. Half-spread from CRSP closing quotes on each
  session (2023-24) or the name's 90th-percentile 2024 CRSP closing half-spread (2025-26; 12 of
  313 names on the 3 bp default). Round trip: 5.2 bp (discovery book), 6.7 bp (held-out book).

## Blocks and funnel

Discovery: entries 2023-03-28 to 2024-12-31, 1,955 events (disjoint megacap and broad names);
1,673 with at least 10 signed contracts in 15:00-15:50; 1,468 in the pool after the 200-event
burn-in; 590 positions in the primary book. Held-out: entries 2025-01-01 to 2026-06-03 (the
latest event on disk), 1,220 events, 964 signalled, all with an outcome; 419 positions.
`block_is_clean` against `research/ledger/blocks.csv` returned clean for both blocks (panel
`flow_atm_ticks`, outcome family `stock_direction_next_session`, feature family
`signed_atm_option_flow`); this lane's views are in `lane_blocks.csv` for the lead to merge.
Attrition: events with fewer than 10 signed contracts move less (mean |move| 3.58% against
4.56%, Mann-Whitney p < 0.001), so the tested set leans to larger movers. The 2025-26 event list
inherits the ledger's drop of events whose exit leg had no bid (large moves).

## Results

Per position, net at the touch, fraction of stock notional, round trip, date-clustered 95%
(clusters on entry date). Nulls are percentiles of the observed mean among random-sign books on the
same events and among random books with the same long and short counts.

| Trial | Rule | Block | N | Net mean [95% CI] | t | Sharpe | Nulls (dir / matched) | Verdict |
|---|---|---|---|---|---|---|---|---|
| 2,712 | declared primary: long top quintile of S, short bottom | discovery | 590 | -0.525% [-1.067, +0.021] | -1.89 | -0.097 | 1.8 / 3.1 | fail |
| 2,713 | same, close-to-open (secondary) | discovery | 591 | -0.496% [-0.896, -0.076] | -2.37 | -0.107 | 1.2 / 2.4 | fail, opposite sign |
| 2,714 | short-straddle selector, sell bottom two terciles of abs(S) | discovery | 1,242 | residual value +0.495% of m0 [-0.902, +1.940] | 0.69 | | cell null 73.3 | fail |
| 2,715 | S residualised on the 15:00-15:50 move | discovery | 514 | -0.549% [-1.104, +0.017] | -1.92 | -0.099 | 2.5 / 3.3 | fail |
| 2,716 | trades of 10+ contracts only | discovery | 465 | -0.316% [-0.907, +0.265] | -1.06 | -0.058 | 15.1 / 17.9 | fail |
| 2,717 | premium-weighted S | discovery | 585 | -0.384% [-0.878, +0.132] | -1.49 | -0.071 | 6.8 / 9.9 | fail |
| 2,718 | reversed book | discovery | 590 | +0.421% [-0.122, +0.964] | 1.52 | +0.078 | 98.4 / 96.9 | fail |
| 2,719 | long-only bottom quintile (post hoc) | discovery | 298 | +0.609% [-0.110, +1.313] | 1.68 | +0.110 | 97.8 / 99.7 | fail |
| 2,720 | last-hour stock move as reversal | discovery | 774 | +0.033% [-0.397, +0.492] | 0.14 | +0.005 | 65.5 / 63.4 | fail |
| 2,721 | reversed book on delta-weighted S | discovery | 593 | +0.335% [-0.180, +0.828] | 1.30 | +0.062 | 95.7 / 93.9 | fail |
| 2,722 | 2,721 with abs(K/F - 1) at most 2% | discovery | 548 | +0.367% [-0.158, +0.887] | 1.38 | +0.068 | 96.5 / 94.5 | fail |
| 2,721 | frozen primary | held-out | 419 | +0.094% [-0.452, +0.631] | 0.34 | +0.016 | 72.1 / 73.2 | fail |
| 2,722 | frozen secondary | held-out | 226 | +0.235% [-0.647, +1.165] | 0.51 | +0.036 | 76.0 / 74.6 | fail |

The selector row (2,714) is the within-cell (causal implied-move tercile by year) difference of
the one-night buy-back B, in units of m0 (0.20 forward plus the 15:59 bid), per trade, net at the
touch, against a cell-matched random null; the selected book itself lost 1.76% of m0
[-2.74, -0.75]. Sources: `trials.csv`, `declared_discovery.log`, `selector_discovery.log`,
`variants_discovery.log`, `heldout.log`, `heldout_result.json`.

Search count: eleven configurations scored on discovery before the freeze (2,712 to 2,722), two
held-out reads of the frozen rules. The frozen primary's discovery t is 1.30; the best discovery
t in the search is 1.68 (2,719, post hoc), which is about what the largest of eleven correlated
null trials would produce.

## What the data say

1. The declared direction is wrong at the margin and not significant. Gross next-session return
   by causal quintile of S on discovery was +0.66%, -0.51%, -0.39%, -0.38%, -0.28% from the most
   bearish flow to the most bullish: not monotone, all in the bottom quintile.
2. The right driver was checked. S correlates weakly with the stock's own last-hour move
   (Spearman +0.083); residualising on it changes nothing (2,715), and the move alone predicts
   nothing (2,720). Whatever the bottom quintile carried on discovery was not the intraday price
   path.
3. The rebound did not replicate. On 2025-26 the bottom quintile lost 0.49% gross (quintiles
   -0.49%, +0.47%, -0.68%, -0.36%, -0.91%), and the frozen book's interval straddles zero with
   both nulls near the 72nd percentile. The conservative reading is that the discovery pattern was
   the noisiest of five bins.
4. As a short-straddle selector, the size of one-sided flow adds no residual value (2,714).
5. Power was limited and was stated before the read: with a 6.5% per-position sd, the held-out
   minimum detectable mean was about 0.93% (80% power). Pan and Poteshman's ordinary-day effect is
   about 0.40% next day. A real effect of literature size would not have been seen here. What the
   held-out read does exclude, at 95%, is a true net mean above about +0.63% per position for the
   frozen book.

## How this differs from the closed studies

- P1 put skew (wrong sign) and the parity-forward premium (no effect) are quote levels; this is
  traded quantity, the flow that should move those levels.
- F2 demand pressure summed signed volume over both legs (net demand for volatility) and scored
  the straddle; this differences the legs (net demand for delta) and scores the stock. Long
  straddle buying adds to F2 and cancels here.
- The 2026-11-10 pre-event direction trials (1,593 to 1,597) used price reversal, card spend,
  seasonality and revision breadth on 2013-18; none used option flow.

## Prior work

- Pan and Poteshman (2006, RFS): open-buy put-call ratios, CBOE data, next-day spread over 40 bp
  (verified, abstract). Their own split says the predictability comes from the non-public
  component; a public-tape signal like this one is the weak part of their decomposition.
- Chan, Chung and Fong (2002, RFS): option net trade volume has no incremental predictive ability
  for quote revisions (verified, abstract). The strongest counter-argument to the lane, and
  consistent with what was found.
- Hu (2014, JFE): option-induced stock order imbalance predicts returns (verified, abstract); the
  closest modern public-tape design, measured through dealers' stock hedging rather than option
  prints.
- Amin and Lee (1997, CAR): more long (short) option positions are opened just before good (bad)
  earnings news (verified, abstract). That result rests on opening transactions, which the tape
  does not identify.
- Johnson and So (2012, JFE), Roll, Schwartz and Subrahmanyam (2010, JFE), Jin, Livnat and Zhang
  (2012, JAR), Muravyev (2016, JF): see `sources.csv` for status.
- The idea is crowded in the literature on daily data with open/close flags; it is untested here
  on intraday quote-signed ATM flow at a 15:50 decision time. None of the papers above measured
  returns net of a stock touch on the earnings night.

## Tradability at Interactive Brokers

The trade is a single-stock market or marketable limit order at about 15:59 and its reverse at
15:59 on the reaction session, one name a night, about 6 bp round trip at the touch on these
names (measured above). The existing harness trades options only; it would need a stock order
path and a borrow check for the short leg. Not verified here: IB's overnight borrow fees for
these names (Johnson and So's mechanism makes the short side's cost central), and whether the
closing auction (MOC entry cutoff about 15:50 ET, recalled) or a 15:59 limit is the better
execution. None of this is worth building on the present evidence.

## The pull that would test the real version

The informed component in the literature needs opening-buy flags and customer origin, which the
OPRA tape does not carry. Cboe's Intraday Open-Close Data (10-minute intervals, by origin, buy or
sell, open or close, on Cboe's four options exchanges only) is priced in SR-CBOE-2026-011: the
existing intraday product at the academic rate is $3,000 for the first year and $250 per extra
month, so March 2023 to October 2026 (44 months) is about $11,000 if the team qualifies; the
one-minute product is $4,000 per request-month at the standard rate. That buys the Pan and
Poteshman signal on a minority of US option volume. Given a held-out interval of
[-0.45%, +0.63%] on the public version and a literature effect of about 0.40%, the pull is not
recommended.

## Not verified

The non-academic price of the 10-minute Open-Close history; the team's eligibility for the
academic rate; IB borrow costs; the MOC cutoff; the abstracts marked recalled in `sources.csv`;
the full texts of every paper cited (abstracts only).

## Files and rebuild

Scripts: `lib.py`, `build_features.py`, `score_discovery.py`, `variants.py`, `make_freeze.py`,
`score_heldout.py` (frozen; refuses a second run). Logs: `diagnosis.log`, `build_*.log`,
`outcomes_discovery.log`, `audit_discovery.log`, `declared_discovery.log`,
`selector_discovery.log`, `variants_discovery.log`, `heldout.log`; results `trials.csv`,
`heldout_result.json`; freeze `freeze_2026-11-14_reversed_delta_flow.md`; block views
`lane_blocks.csv`. The per-event parquet intermediates held vendor-derived prices and were
deleted; rebuild with `build_features.py --block discovery|heldout` and
`score_discovery.py --outcomes` (a few minutes, cached data and one R2 read, no spend).

Folder: `C:\Users\jodor\Documents\QUANTT_IVCrush_Project\outputs\research\2026-11-14-earnings-adjacent-hunt\E2-informed-flow\`
