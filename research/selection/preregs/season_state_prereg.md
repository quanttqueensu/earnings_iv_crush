# Pre-registration: sequential earnings-season state

Frozen before any regression is run. One trial. No threshold, no search, no ML, no
second predictor. If it fails, it fails.

## Hypothesis

The direction of the earnings-volatility premium is not constant. Each earnings season
carries a latent shock intensity that the option market does not know at the start of the
season and learns during it. Early reporters in a season reveal information about the
distribution of later reporters' event moves within the same season.

Operationally: the average realised-versus-implied error of the events that have already
reported this season predicts the executable return of the next short straddle in that
season.

The null is that no pre-event variable observable at entry predicts the straddle's return,
and in particular that a season's own partial history does not.

This is distinct from every trial in the 1,476-trial record. Those select **events**
(term spread, move gate, skew, curvature) or **names** (richness persistence). This
conditions on **time**, and it admits a negative coefficient, meaning the correct trade in
a violent season may be the opposite of the correct trade in a calm one. An unconditional
short-volatility book cannot express that, which is a candidate explanation for why every
unconditional variant has failed.

## State variable

For event *j* in season *q*, using only events in the same season with a strictly earlier
announce date:

    S(j,q) = mean over prior i in q of ( |realised move_i| / implied move_i  -  1 )

`S > 0`: earlier reporters moved more than the options implied, so sellers were hurt.
`S < 0`: earlier reporters moved less than implied, so sellers were paid.

**Season** is the calendar quarter of the announce date. Declared in advance and not
varied. This splits a reporter on 31 March from one on 1 April, which is a known and
accepted cost of a rule fixed before seeing anything.

**Minimum priors.** An event is scored only if at least **5** events in its season already
reported. The first five of every season are unscorable by construction.

**Universe for the state.** The same executable book, pooled across all names. Not
sector-conditioned. The sector version is explicitly a second-stage test that does not run
unless this one survives, and it would be a separate trial.

## Payoff

Executable return on margin. The straddle is marked at the entry strike, held fixed, from
both legs' consolidated quotes at 15:59 exchange-local on the entry and exit sessions,
through the existing marking path. Two cost arms, both reported:

1. **Gross.** No frictions. This answers the economic question of whether the payoff is
   predictable.
2. **Measured.** Fixed-boundary execution from the 34,672-print study: 1.2714% of premium
   at entry and 3.0182% at exit, asymmetric, applied as half a quoted width.

Neither arm may be preferred after the fact. The measured arm governs any tradability
claim; the gross arm governs the existence claim.

## Specification

Ordinary least squares, one predictor, no controls, no intercept suppression:

    R(j,q) = alpha + beta * S(j,q) + e(j,q)

Both `R` and `S` are winsorised at the 1st and 99th percentiles within each estimation
window, declared here so the choice cannot be made after seeing the tails.

Terciles of `S` with their mean return and hit rate are reported as **descriptive output
only**. They are not a second test and monotonicity is not a criterion; a threshold
strategy is explicitly not being fitted.

## Blocks

Three, all reported, none dropped:

| Block | Events | Role |
|---|---|---|
| 2019-2024 | megacap, trade-marked | discovery |
| 2022-2024 | subset of the above | out-of-sample within discovery |
| 2013-2018 | megacap, quote-marked | disjoint replication |

The 2013-2018 block is a true holdout in the strongest sense available: the frozen event
gate produces per-trade Sharpe -0.005337 there, so it is not a regime the project has
already tuned into.

## Inference

Bootstrap, 5,000 draws, seed 0, resampling whole clusters and refitting the slope inside
each draw.

**Primary: season-clustered.** The state variable is strongly autocorrelated within a
season, so the effective sample size is closer to the number of seasons than to the number
of events. 2019-2024 contains roughly 24 seasons. A season-clustered interval will
therefore be wide, and that width is the honest measurement, not a defect to be
engineered away.

**Also reported:** name-clustered, and a two-way season-by-name interval via the additive
decomposition `V_season + V_name - V_iid`.

## Decision rule, declared in advance

The result is called **positive** only if all three hold:

1. The slope has the **same sign** in 2019-2024 and in 2013-2018. Two disjoint six-year
   blocks disagreeing on sign is a fatal result for a state-dependence claim, because the
   claim is precisely that the state is what carries the information.
2. The season-clustered 95% interval on beta excludes zero in **2019-2024**.
3. The sign survives on the **gross** arm. Cost cannot create a slope, so a slope that
   only appears net of frictions is a cost-model artefact.

Anything short of all three is negative or inconclusive, reported with the achieved N and
the achieved number of season clusters.

## Declared in advance as non-decisive

The 2022-2024 sub-window on its own; tercile monotonicity; the R-squared; any single
season; and the absolute level of the book's return, which is a separate question already
settled negatively.

## Known hazards this run inherits

The stale entry spot is unrepaired on 16.9% of priced events and affects strike selection,
marks and sizing. Roughly 18% of events in the comparable name-persistence run were
unmarkable or sized to zero contracts; the same funnel is reported here rather than
silently shrinking the sample.

Season count is the binding constraint on power, not event count. This is stated before
the run so that a wide interval is read as low power rather than as evidence of absence.

## Trial accounting

One trial. It is charged to the deflation count whatever the outcome.
