# P5: short strangle at plus or minus one implied move

## Hypothesis, scope and success criteria

Selling the wings rather than the centre trades less gap convexity near the money and may earn more
per unit of margin if out-of-the-money event options are priced rich (Alexiou, Goyal, Kostakis and
Rompolis, Review of Finance 2025, on concave pre-announcement smiles). Pre-registration
`_private/p5_strangle_prereg.md` (SHA-256 58b3e998...) and amendment 01 (SHA-256 637ad0c7..., pairs
the strangle with a straddle priced identically on the same chains), both before any outcome.
Strikes: the nearest listed strikes at or beyond F(1 +/- implied move); sold at the 15:59 entry bids,
bought back at the 15:59 exit asks; Reg-T strangle margin. Pass required (i) mean net strangle RoM
above zero with a date-clustered 95% interval above zero and (ii) the paired strangle-minus-straddle
difference above zero with its interval above zero; the handbook's kill rule is a failure of (ii).

## Funnel and a selection problem

| Step | Events |
|---|---|
| 2025-2026 ledger | 1,221 |
| No strike at or beyond F(1 +/- m) in the cached entry chain | -365 |
| A required leg absent or unusable at entry or exit | -760 |
| Empty book | -2 |
| **Scored** | **94** (66 entry dates) |

The cached 15:59 chains in `data/cache/backfill_chains` cover a strike window around each day's own
spot. When the stock moves a long way, the exit chain no longer carries the entry strikes, so the
loss of events depends on the outcome. The scored events had realised moves of 0.47 of the implied
move on average against 0.61 for the dropped events, and a ledger net RoM of +1.91% against +0.37%.
The scored sample is tilted toward small moves, which flatters both structures and the strangle
most.

## Results (biased sample, N=94)

| Measure | Value |
|---|---|
| Strangle net RoM per trade | +3.71% [+0.40%, +6.21%] |
| Straddle net RoM per trade, same pricing | +3.29% [+0.98%, +5.42%] |
| **Paired difference (strangle minus straddle)** | **+0.42% [-1.04%, +1.53%]** |
| At the mid: strangle / straddle | +4.74% / +4.68% |
| Entry half-spread as a share of premium: strangle / straddle | 4.5% / 2.5% |

## Verdict

**FAIL on the kill rule (ii).** Criterion (i) passes only on a sample selected for small moves and is
not evidence. Criterion (ii) is the less biased comparison, since both structures face the same
selection, and the strangle does not beat the straddle even where the selection favours it: the
two are level at the mid, and the strangle's wider relative spread (4.5% of premium against 2.5%)
takes away what the wings save. P5 is closed under its pre-registered rule.

A clean test of (i) would need complete exit chains for every entry strike; Databento `cbbo-1m` on
the four contracts per event is the source, and it is metered.

## Reproduction

```
python scripts/research_p5_strangle.py
```
