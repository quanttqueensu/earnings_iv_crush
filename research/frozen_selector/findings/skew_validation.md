# Skew lever - out-of-sample validation (Databento OPRA, 2019-2023)

> **Standing: still valid, and decisive.** This is the doc that rejected the skew gate out of
> sample (DSR 0.00), overturning the in-sample "doubles the Sharpe" claim in
> [`signal_research_memo.md`](signal_research_memo.md) and
> [`orthogonal_pairings.md`](orthogonal_pairings.md). It agrees with the current verdict: term
> gate alone, per-trade Sharpe +0.12, not significant, with a clean cross-market negative.
> Full state: [`../_private/standing.md`](../_private/standing.md).

**Hypothesis.** The term and low-skew gates, tuned on the 2024-2026 sample, still
separate good short-straddle events from bad ones on the pre-2024 OPRA sample - a
different period (incl. the 2020 COVID shock and 2022 bear), so a genuine
out-of-sample test.

**Sample.** 702 causal-window events, 40 megacap names, 2019-02-01 to 2023-12-19.

**Result (frequency-neutral vs the Agent-0 control).**
- term-only: per-trade Sharpe -0.616 (delta vs control +0.060) on 193 trades.
- term+skew: per-trade Sharpe -0.593 (delta +0.083) on 123 trades.
- best arm 'full_stack': size-matched 95% CI [-1.44, +3.44], deflated Sharpe 0.00.
- keep-fraction sweep is NOT a plateau (gated cuts vs term-only).

**Verdict.** The size-matched CI straddles zero, so the skew lever is NOT validated out of sample; treat as suggestive, not established. Moreover, every arm's absolute per-trade Sharpe is negative: on this 2019-2023 sample the short-straddle book loses money per trade, and the gates only shrink the loss rather than turn it positive. The in-sample edge does not generalise to the COVID/2022 regimes - it is regime-dependent, not established.

**Caveats.** Pre-2023 marks are trade-based daily closes (no NBBO mid), so wing-strike
skew is patchier than ATM; one liquid-megacap universe; bootstrap-only significance.
The term gate here is the panel-free
cross-sectional term-spread quantile, not the per-name trailing-day panel of the
in-sample run (the daily OPRA panel is cost-prohibitive to reconstruct); the two are
both causal but not identical. A longer multi-name history (WRDS/OptionMetrics) with the
trailing-day panel remains the stronger test.