# The final earnings test set: all three fail, and the failures locate the premium

Pre-registration `_private/final_earnings_set_prereg.md` (SHA-256 in
`../prereg_final_earnings_set.json`), declared as the final set for the single-name earnings straddle.
Three trials; DSR against 1,494. Script: `scripts/research_final_earnings_set.py` (T3 in
`scripts/research_retail_share.py`).

## T1. Spread gate on the 2025-2026 broad block: fails, and the premium moves with the toll

| book | N | touch net per trade | Sharpe [CI] | gross at mid | expected cost |
|---|---|---|---|---|---|
| gated | 141 | -3.02% | -0.224 [-0.367, -0.046] | -0.34% | 0.086 |
| ungated (eligible) | 381 | -3.29% | -0.283 [-0.383, -0.172] | +1.03% | 0.172 |

Return on margin; eligible events need three earlier completed events of the same name inside the
block, which leaves the later 381. The gate halves expected cost, as designed, but the gated events'
gross premium is negative: on this sample the low-cost events carried no premium to keep. The
gated book sits at the 85th percentile of 1,000 matched random draws.

## T2. Risk-normalised sizing: fails, mechanism check fails

Weights inversely proportional to each straddle's risk on Reg-T margin, normalised to mean one.

| block | N | Sharpe unweighted | Sharpe weighted [CI] | difference CI |
|---|---|---|---|---|
| 2019-2024 megacap | 839 | -0.0220 | -0.0269 [-0.0909, +0.0430] | [-0.0241, +0.0136] |
| 2013-2018 megacap | 955 | -0.0368 | -0.0496 [-0.1105, +0.0128] | [-0.0346, +0.0089] |
| 2025-2026 broad | 1,221 | +0.0431 | +0.0426 [-0.0257, +0.1179] | [-0.0134, +0.0124] |

Return per unit of ex-ante risk is slightly lower in the low-risk events, so the premise that
premium scales one-for-one with risk does not hold and equal-risk weighting has nothing to exploit.
The broad block's unweighted figure reproduces the settled +0.0431.

## T3. Retail ownership: fails at discovery

One minus 13F institutional ownership, lagged 45 days. 2019-2024 megacap, N=839: decile Spearman
+0.236 (required +0.60), top-minus-bottom quintile +0.56% of margin, CI [-2.15%, +3.38%], premium
share of the gap 5.87 (the gap that exists is premium collected). Retail share spans roughly 17% to
40% across megacap quintiles, little range to sort on. Not carried to validation.

## What the failures say together

The cost-side evidence is consistent across blocks: the announcement premium is gross-positive and
is paid away at the touch, the gate can halve the toll but cannot find premium where there is none,
and neither sizing nor a retail-ownership proxy changes the per-trade economics. On the decision
rule as amended, the single-name earnings straddle stops being the vehicle.

An exploratory sort of the full 2025-2026 block by **entry** half-spread (known at entry) found
the tightest tercile positive at the touch (+1.69% of margin, Sharpe +0.116, CI [+0.008, +0.239],
N=407), with gross premium similar across terciles. It was found after T1 failed, on a heavily used
block, with in-sample cut-offs, and it contradicts the megacap evidence (similar spreads, negative at
the touch). It is under a separate pre-registered test on fresh DoltHub 2019-2024 data and carries
no weight unless that test passes.

## Artefacts

| File | Content |
|---|---|
| `t1_spread_gate_broad.csv` | T1 gated and ungated books |
| `t2_risk_sizing.csv` | T2 per block |
| `t3_retail_share.csv` | T3 discovery statistics |
