# A frozen machine-learned predictor of realised over implied earnings move

## Hypothesis, scope and success criteria

Single at-entry variables have each failed to select better earnings straddles. A model combining
them might still rank events by how much of the implied move will be realised, the mispricing the
short straddle earns. Pre-registration `research/selection/preregs/ml_ratio_prereg.md` (SHA-256 e84cefb3...) and
amendment 01 (seven listed candidates, nine trials charged), frozen before training. Target:
realised/implied move. Fifteen features known at the entry close (term structure, skew, kurtosis,
trailing volatility, volatility premia, tenor, log implied move, implied over daily realised
volatility, the date shift, and the name's prior realised/implied). Train on megacap events
2013-2018, choose on 2019-2021, refit on 2013-2021, freeze the model and a sell threshold (20th
percentile of in-sample predictions), then open the 2022-2024 megacap test and the
attrition-corrected 2025-2026 broad confirmation once each. Both must pass: Spearman(prediction,
realised/implied) above zero with a date-clustered interval above zero; selected events' mean net
RoM above the 95th percentile of random selections of the same size; selected mean above zero.

Prior work: Gu, Kelly and Xiu (RFS 2020); Bali, Beckmeyer, Moerke and Weigert (RFS 2023) on
machine-learned option return prediction. Neither study targets the earnings event straddle.

## Model selection (validation 2019-2021)

| Candidate | Validation Spearman |
|---|---|
| Ridge, alpha 1 / 10 / 100 | +0.130 / **+0.141** / +0.128 |
| Gradient boosting, depth 2 or 3, 100 or 300 iterations | +0.083 to +0.099 |

Ridge with alpha 10 won; the boosted trees did worse, so there is little non-linear structure to
find. Frozen model SHA-256 884e149d...; threshold 0.72618.

## Results (opened once)

| Set | N | Selected | Spearman [95% CI] | Selected net RoM [CI] | All events | Random-selection percentile |
|---|---|---|---|---|---|---|
| Megacap 2022-24 (test) | 429 | 64 | -0.040 [-0.139, +0.061] | +0.19% [-3.11%, +3.22%] | -0.91% | 77th |
| Broad 2025-26 (confirmation) | 1,449 | 887 | +0.113 [+0.055, +0.168] | +2.02% [+1.15%, +2.84%] | -1.12% | 100th |

Broad selected book: per-trade Sharpe +0.183, DSR 0.99999 against 1,520 trials.

## Verdict

**FAIL under the pre-registered rule**, because the megacap test fails. The broad confirmation passes
on every criterion.

## Robustness of the broad result (descriptive, after the verdict)

- **Attrition.** On all 1,941 broad events, using realised/implied from the event file (no exit
  marks needed, so the events the ledger dropped are back in), Spearman is +0.126 and the selected
  events' realised/implied is 0.65 against 0.84 for the rest.
- **Actual execution.** On the 1,083 broad events with tick data, at the real 15:59 touch, selected
  events earn +1.53% of margin per trade and unselected lose -3.24%; with resting orders the
  selected book earns +2.75%.
- **Stability.** 2025: selected +2.88%, unselected -6.42%. 2026 (to June): selected +0.28%,
  unselected -5.69%. The model mainly identifies events to avoid.
- **Tenor confound.** The largest coefficient is on time to expiry, which mechanically lowers
  realised/implied for longer-dated straddles. Within each tenor band (0-3, 4-7, 8-14, 15-60 days)
  selected events beat unselected by 6 to 11 points of margin, so tenor does not carry the result.

## Reading

The model generalises from megacaps to the broad universe in 2025-2026 but not to megacaps in
2022-2024, where it selects few events (64 of 429) and ranks them no better than chance. Two
readings fit: the broad universe has more cross-sectional dispersion in the features to exploit, or
the broad pass is a block-specific result. A separately declared second confirmation on
July-August 2026 events, never used anywhere in the programme, is the test that separates them
(`research/selection/preregs/ml_ratio_confirm2_prereg.md`).

## Reproduction

```
python scripts/research_ml_ratio.py --select
python scripts/research_ml_ratio.py --test
```
