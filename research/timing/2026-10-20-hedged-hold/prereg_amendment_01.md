# Amendment 01 to the hedged-hold pre-registration: the declared second wave

Frozen after the S1 and S3a discovery results were viewed (both failed) and before any S2, S3b or
second-wave outcome was viewed. Record:
`outputs/research/prereg_2026-10-20-hedged-hold_amendment_01.json`. The original text declared
this wave and its trigger (fewer than three passing candidates); this file fixes its exact
specification. Every rule not stated here is the original's: data, blocks, hedge, costs,
settlement, margin, funnel, bootstrap, staging and kill criterion.

## W2a. S1 at 46 to 120 days

The S1 position with the sold expiry the shortest one with 46 to 120 days from the entry date
that expires on or after the exit date. Jump split: the front expiry (shortest on or after the
exit date) and the sold expiry. Pass rule as S1. Rationale for running despite S1's failure: the
original declared it, and a longer hold collects more diffusive premium per half-spread; the
dilution argument against it is the expected outcome and is stated in advance.

## W2b. S2 selected by the post-event term slope

Signal: ATM implied vol on the shortest expiry at least 21 days after the S2 sold expiry, minus
ATM implied vol on the sold expiry, both at the exit 15:59 chain (the `post_slope` feature).
The seller's preferred tercile is the lowest slope (front richest relative to the next expiry,
the short leg of Vasquez 2017). Causal terciles on exit dates, minimum 200 prior events. "Top" in
the selector rule means the lowest-slope tercile. Outcome and pass rule as S3.

## W2c. GARCH(1,1) with an announcement dummy in place of HAR

Applied to the S3 arm with the higher discovery top-minus-bottom point estimate (S3a: -0.732;
S3b: whichever its discovery run prints), chosen mechanically by that rule.

Model: r_t = e_t, sigma2_t = omega + alpha e_{t-1}^2 + beta sigma2_{t-1} + delta D_t, where r_t is
the daily log return and D_t = 1 on the name's reaction (exit) dates. Gaussian quasi-maximum
likelihood (scipy L-BFGS-B, omega, alpha, beta, delta >= 0, alpha + beta < 1), initialised at the
sample variance. Parameters are refitted per name at the start of each calendar quarter on all
returns strictly before that date, minimum 500 returns. At each decision the variance is filtered
with those parameters through the last return before the decision date, then forecast h steps with
D = 0 (h as in the original), summed and annualised by 252 / h. The signal is the arm's implied
variance numerator over this forecast. Everything else as the chosen S3 arm.

## Trial accounting

Three trials. Count after: 1,542. DSR inputs for this wave: 1,542 trials, trial-Sharpe dispersion
0.127475.
