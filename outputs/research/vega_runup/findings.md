# Pre-announcement vega run-up (state of record section 2.5)

## Hypothesis, scope and success criteria

Front-expiry implied volatility rises into an announcement (Patell and Wolfson 1979, 1981;
Dubinsky, Johannes, Kaeck and Seeger RFS 2019), and Gao, Xing and Zhang (JFQA 2018) report positive
returns on straddles bought shortly before announcements. A long at-the-money straddle bought three
to six sessions before the last pre-news snapshot and sold at that snapshot holds no gap risk. The
counter-argument was stated in advance: with a fixed expiry the event variance is already in the
price, the rising front IV is largely that fixed variance over a shrinking tenor, and theta works
against the holder.

Pre-registration `_private/vega_runup_prereg.md` (SHA-256 1fce8039...) with amendments 01 and 02
(sampled snapshots; expiry present in both snapshots), all frozen before any outcome. Data: free
DoltHub end-of-day chains, 2019-2024, 1,421 S&P 500 events (tickers A to CHD), with a matched null
window on the same name 30 sessions after each event. Pass required (i) mean long return at the touch
above zero with a date-clustered 95% interval above zero and (ii) the event-minus-null paired
difference above zero with its interval above zero.

## Funnel

| Step | Event windows | Null windows |
|---|---|---|
| Windows | 1,421 | 1,418 |
| No exit snapshot within two sessions of the anchor | -206 | -237 |
| No entry snapshot three to six sessions earlier | -3 | -1 |
| No expiry after the event present in both snapshots | -117 | -266 |
| Strike leg missing in one snapshot | -173 | -146 |
| **Priced (primary)** | **922** | **768** |
| Paired with a priced null | 597 | |

Holds: 3 sessions (839), 4 (60), 5 (23). The expiry used is usually the shared monthly, so tenors are
longer than the front weekly the run-up is strongest in, which works against the hypothesis.

## Results

Per trade, on entry mid premium.

| Measure | Value |
|---|---|
| Long straddle at the touch, net | -11.72% [-13.09%, -10.34%] |
| Long straddle at the mid, gross | +0.77% [-0.30%, +1.92%] |
| Matched null at the touch | -15.03% (N=768) |
| **Paired event minus null, touch** | **+3.54% [+0.51%, +6.46%]** (N=597) |
| Mean entry half-spread, share of premium | 5.87% |
| Mean change in the contract's IV over the hold | +2.69 vol points |
| Mid return per vol point of IV change (OLS slope) | +0.77% per point, intercept -1.30% |
| Per-trade Sharpe at the touch | -0.70 (DSR 0.000) |
| D-1 to D-2 entry variant (secondary), touch / mid | -12.22% / +0.27% (N=941) |

By year, touch: 2020 -14.8%, 2021 -13.4%, 2022 -13.4%, 2023 -10.1%, 2024 -6.9%.

## Verdict

**FAIL** on criterion (i). The run-up is real in implied volatility (+2.7 points over three
sessions) and event windows do better than ordinary windows on the same names (+3.5 points, interval
above zero), but the gain is almost exactly offset by theta: at the mid the trade earns +0.77% with
an interval spanning zero, and the regression intercept (-1.30% at zero IV change) is the decay the
holder pays. A liquidity taker then pays about 5.9% of premium on each side. This is the stated
counter-argument holding: a fixed-expiry straddle does not gain from a run-up that is mostly fixed
event variance over a shrinking tenor.

## First objections

**Quote quality.** DoltHub end-of-day quotes may be wider than the 15:59 consolidated quotes used
elsewhere; the mid arm, which does not depend on the spread, already shows no premium.
**Tenor.** The shared-expiry rule pushes tenors toward the monthly; the front weekly would carry a
larger run-up but also faster decay, and the free source cannot price it reliably.
**Universe.** Alphabetically truncated (A to CHD), unrelated to outcomes.

## Reproduction

```
python scripts/research_vega_runup.py --pull --workers 3
python scripts/research_vega_runup.py --score
```
