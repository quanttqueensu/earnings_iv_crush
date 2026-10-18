# Post-announcement short straddle held to expiry

## Hypothesis, scope and success criteria

After the announcement, the next listed expiries may still price more volatility than the stock
then realises (single-stock variance risk premium: Goyal and Saretto, JFE 2009; Cao and Han, JFE
2013). Selling the at-the-money straddle at the exit-day 15:59 ET and holding it to expiry pays one
entry half-spread and settles at intrinsic, so it avoids the 3.02% exit spread that sank the event
book. Pre-registration `research/timing/preregs/post_event_vrp_prereg.md` (SHA-256 3cbc2b46...), frozen before any
price was computed. Pass required mean net return on margin per trade above zero with a 95% interval
above zero, clustered on expiry date, and a positive implied-minus-realised volatility gap that rises
with P&L.

Block: 2025-2026 S&P 500 earnings events; expiry the shortest with 14 to 45 days to run (mean 19.1);
strike nearest the parity forward; sold at the bids; USD 0.65 per contract per leg; 5 bp to dispose
of delivered stock; Reg-T margin 0.2 S + premium.

## Settlement-price correction (found after the first scoring, disclosed here)

The first scoring settled against yfinance closes, which are split-adjusted to today even with
`auto_adjust=False`, while strikes are on the entry-date share basis. Names that split after the
trade (BKNG 25:1, ORLY 15:1, NFLX 10:1) produced losses several times margin, which is how the error
was found. A ratio heuristic then left a spin-off adjustment (DD) wrong. The final scoring settles on
Alpaca's free historical consolidated daily closes with `adjustment=raw`, applies a split factor only
if a clean split falls inside the holding window (none did), and drops events with any other
corporate action inside the window (2). The pre-registered rule, sample and costs are unchanged. All
three runs fail; their summaries are kept (`summary_before_split_fix.json`,
`summary_split_heuristic.json`, `summary.json`).

| Run | Mean net RoM per trade | 95% CI |
|---|---|---|
| yfinance closes (wrong basis) | -8.37% | [-10.71%, -5.99%] |
| Split-ratio heuristic | -1.97% | [-3.88%, -0.30%] |
| **Raw consolidated closes (final)** | **-1.41%** | **[-3.23%, +0.20%]** |

## Results (final)

| Measure | Value |
|---|---|
| Trades (expiry clusters) | 1,888 (74) |
| Mean net RoM per trade | -1.41% [-3.23%, +0.20%] |
| Median net RoM | +2.62% |
| Mean RoM at the mid (gross of the entry spread) | +0.55% [-1.25%, +2.13%] |
| Mean return on premium, net | -7.0% |
| Per-trade Sharpe, net | -0.077 (DSR 0.0002 against 1,504 trials) |
| Entry half-spread as a share of premium | 7.9% |
| Implied minus realised volatility | +2.27 vol points [+1.12, +3.25] |
| Spearman(P&L, volatility gap) | +0.27 |
| Excluding entries 2025-03-15 to 2025-04-30 (descriptive) | -0.79%, N=1,706 |
| Maximum concurrent positions | 251 |

Largest losses (fraction of margin): ENPH 2026-04-29 -1.92, INTC 2026-04-24 -1.27, FSLR 2025-04-30
-1.13, MU 2025-03-21 -0.92.

## Verdict

**FAIL** on the P&L criterion. The mechanism is present: post-announcement implied volatility
exceeds subsequent realised volatility by about 2.3 points on average, and P&L rises with the gap.
But at the mid the book is only +0.55% of margin per trade with an interval spanning zero, because a
few large post-event moves offset the steady premium, and the entry half-spread (7.9% of premium)
turns it negative. This is the programme's recurring pattern in a new form: the premium exists and
is paid away at the touch. A resting-order entry would at best recover the mid result, which is not
distinguishable from zero.

## First objections

**Clustering.** Expiry-date clusters are the conservative choice for positions that share a
terminal move; 74 clusters are enough for a percentile bootstrap but not generous.
**Early assignment.** Calls were not modelled for early exercise before ex-dividend dates; the
effect is small at these tenors and would make the result worse, not better.
**Regime.** The block includes the April 2025 sell-off; excluding it moves the mean to -0.79%,
still negative, and the exclusion is descriptive only.

## Reproduction

```
python scripts/research_post_event_vrp.py
```
