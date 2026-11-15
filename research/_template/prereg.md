# Pre-registration: <title>

Frozen before any outcome for the declared blocks is computed. Changes after an outcome is viewed
require a dated amendment with its own hash. Record: `outputs/research/prereg_<slug>.json`.
Scorer: `research/<line>/<slug>/study.py`.

## Hypothesis

One falsifiable statement.

## Mechanism

The economic or microstructure reason it would be true, stated before any data for the declared
blocks was viewed. A result without an accepted mechanism stays exploratory however significant.

## Data and blocks

Source, universe, dates. Discovery, validation and confirmation blocks, and which of them have
had outcomes viewed for any earlier study.

## Specification

Every rule that turns data into a position, with each parameter's value and how it was derived
(not swept). The causal alignment of every feature.

## Primary statistic and inference

The statistic, its unit and basis (per trade, net at the measured cost, on margin), the
date-clustered bootstrap (5,000 draws, seed 0), and the matched random null if it is a selector.

## Power

The minimum detectable effect at 80% power for each block (`protocol.min_detectable_effect` or
`min_detectable_rate_ratio`), from data viewed before, against the effect the mechanism implies.
One line on why the primary statistic can answer the question given the outcome's known sign and
scale (a Sharpe comparison cannot rank weightings of a book whose mean is negative).

## Block history

For each declared block, the result of `protocol.block_is_clean` and any ledger rows it returned.

## Success criterion

The exact condition for a pass at each stage. Confirmation also needs t >= 3 and the p-value passing
Benjamini-Hochberg at 5% within the slate; the LOND alpha is recorded beside it as advisory
(`docs/PROTOCOL.md` P20). Blocks are scored in order and scoring stops at the first failure.

## Kill criterion

The exact condition that closes the idea, stated so a failure cannot be reread as a pass.

## Trial accounting

Trials declared by this study, and the count after it.
