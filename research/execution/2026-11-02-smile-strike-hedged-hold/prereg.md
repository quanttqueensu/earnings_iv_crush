# Pre-registration: where in the event smile the hedged holder is paid

Frozen before any strangle outcome is computed. Record:
`outputs/research/prereg_2026-11-02-smile-strike-hedged-hold.json`. Scorer:
`research/execution/2026-11-02-smile-strike-hedged-hold/study.py`.

## Hypothesis

Before an announcement the front smile carries the event as a jump, and its shape near the money
is set by the market's bimodal event density (Alexiou, Goyal, Kostakis and Rompolis, Review of
Finance 2025, concave curves; Glasserman and Pirjol 2023, W-shaped curves). The hedged event hold
(prereg 3e80d470) sells the ATM straddle, which is short the whole density; the Greek attribution
of the one-night trade shows its losses concentrate in moves above about twice the implied move,
while the typical move is smaller than implied. A strangle with strikes one implied move either
side of the forward sells only the density beyond the typical move and is flat inside it. Under
the hedged hold, which pays no option exit spread, the question is whether the overpricing lives
in the body (straddle better) or in the tails (strangle better).

Hypothesis: the hedged one-implied-move strangle (arm G) has a higher per-trade Sharpe than the
hedged ATM straddle (arm H) on the same events, and its own per-trade Sharpe is positive.

Closest prior work. P5 (`selection/findings/p5_strangle.md`) compared a strangle with the straddle
on the one-night buy-back: no difference, N=94, biased by exit attrition. Wings and iron flies
(`docs/reference/RESEARCH_RECORD.md` 6.2) were long wings, net negative. The skew, kurtosis and
curvature gates selected events, not strikes. This study fixes the event set and changes only the
strikes, under an exit that removes the attrition and the exit spread that sank P5.

## Data

Events: every `ok` event of the hedged event hold, 2013-24
(`outputs/research/2026-11-02-hedged-event-hold/events.parquet`), whose arm H is taken as frozen.
Entry and reaction chains: `data/cache/backfill_chains/{ticker}_{date}.parquet` (Databento OPRA
consolidated quotes, last record at or before 15:59 ET). Stock: CRSP through
`study.stock_path` of the hedged event hold, unchanged. Blocks: discovery 2013-18, validation
2019-24.

## Specification

- Implied move `IM = front_mid / front_fwd` (the ATM straddle mid over the parity forward, from
  the frozen features file).
- Call strike: the smallest listed front-expiry strike at or above `fwd x (1 + IM)` whose entry
  call bid is > 0. Put strike: the largest at or below `fwd x (1 - IM)` whose entry put bid is > 0.
  If either is missing, the event is dropped as `no_wing`, counted.
- Sale: both legs at their entry 15:59 bids; mid credit at their mids (two-sided legs only).
- Hedge, as in arm H: no hedge on the entry night; from the reaction close, hold `+delta` shares
  against the short strangle at every close up to the session before expiry, Black-Scholes delta
  of each leg on the close with zero carry; equity half-spread from CRSP, floored at 1 bp; hedge
  P&L on total returns; unwound at the settlement close.
- Hedge volatility per leg: the implied volatility of that leg's reaction-session 15:59 mid on the
  parity forward of the reaction chain (two-sided only); else that leg's entry implied volatility,
  counted as `entry_iv_fallback`; else dropped as `no_hedge_vol`.
- Settlement: intrinsic `max(S - Kc, 0) + max(Kp - S, 0)` on the CRSP close of the expiry session;
  5 bp disposal when either leg is in the money; commission USD 0.65 per contract on the two entry
  legs only.
- Unit: own margin `mG = 0.20 x fwd + strangle sale` (the same Reg-T approximation as arm H's
  `m0`). Arm H is per `m0`. Each arm's per-trade Sharpe is unit-free within the arm.
- Expiries on the reaction session: no hedge, settle at intrinsic, as in arm H.

## Statistics (date-clustered by reaction date, 5,000 draws, seed 0)

- P1: per-trade Sharpe of G, validation block (2019-24), and its point in discovery.
- P2: paired difference `Sharpe(G) - Sharpe(H)` on the events where both exist, resampling event
  indices within whole dates, in each block.

## Criterion

- BOOK PASS: P1 validation interval excludes zero above, and the discovery point is > 0.
- STRUCTURE LEVER: P2 interval excludes zero above in both blocks.
- Otherwise FAIL; a P2 interval below zero in both blocks reads "the straddle is the better
  structure".
- Attrition guard: if mean H on the G-kept events exceeds mean H on all H events by more than
  0.5% of m0 in either block, P1 is reported as biased and not read.

## Secondary (descriptive, not trials)

Mean G at the mid and net on mG; per-leg (call and put) contribution; G minus H by move ratio
(|reaction move| / IM) bins; entry half-spread of the strangle against the straddle as a fraction
of premium; skew and worst 1%; DSR of G against 1,557 trials.

## Trial accounting

One trial: 1,556 + 1 = 1,557. A pass would be confirmed on 2025-26 under a separate amendment
before any claim.
