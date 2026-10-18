# 0003. The forward book trades the unconditional rule, on paper only
*Date: 2026-10-18 · Status: Accepted*

**Context:** The 2026-10-06 decision rule fired: the conditional hold and the causal spread gate
both failed, and every liquidity-taking version of the earnings straddle fails net. The one
question no backtest can answer is how much of the spread a mid-seeking ladder recaptures on
real order lifecycles, and whether its fills are adversely selected.

**Decision:** The paper book trades every eligible event on the 346-name universe, unconditionally,
leg by leg through the mid-to-touch ladder, one-session hold, as specified in
`docs/FORWARD_TEST_SPEC.md`. It never trades real money; the connection refuses every live port.
No selector enters the forward book until it has passed its own pre-registered backtest and beaten
the matched random null.

**Evidence:** `docs/RESEARCH_STATE.md`; the maker study's broad-block improvement of +2.06% of
margin per trade with a -0.68 markout (`research/execution/findings/flow_liquidity.md`) is the
backtest's best estimate of what the ladder could recapture and of the adverse selection it
faces.

**Consequences:** The verdict needs about 600 trades (about four seasons); the futility stop in
the specification can end it sooner.
