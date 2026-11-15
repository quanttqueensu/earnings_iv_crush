# Forward Test Addendum: Resting Entry and Hedged Hold

Author: Jordan Odorico

Proposed amendment to `docs/FORWARD_TEST_SPEC.md`. It is not adopted until the analyst merges it
into that document; until then the paper book runs the specification as written. Nothing here
changes the rule's event selection, the session guards (section 3) or the hard limits (section 4).

## 1. Hypothesis, scope and success criteria

**Evidence it rests on.** Two levers measured on real quotes, each with its own limits.

- Exit lever (hedged hold, prereg 3e80d470, amendments 91293d96 and c8bcca6c). Replacing the
  reaction-session buy-back at the 15:59 asks with a daily stock hedge held to expiry improves the
  per-trade result by +2.06% [+1.82, +2.31] of m0 (2013-18, N=2,640), +1.68% [+1.40, +1.96]
  (2019-24, N=5,113) and +2.75% [+2.37, +3.11] (2025-26, N=1,597). Unit: per trade, fraction of
  `m0 = 0.20 x forward + entry bid`; date-clustered 95% intervals. Most of it (+1.7 to +1.8
  points) is the exit half-spread no longer paid.
- Entry lever (prereg 53aa4898). Resting each leg at the 15:00 mid and crossing unfilled legs at
  15:59:00 improves entry by +0.89% [+0.77, +1.01] of m0 per trade (2025-26 ledger contracts,
  N=1,136, strict fill rule, no queue model). F1 had already seen fills on this block.

The hedged-hold book itself is not established: its per-trade Sharpe is -0.007 [-0.067, +0.052]
in 2025-26 and negative in both earlier blocks. Adding the entry lever gives an imputed +0.64% to
+0.79% of m0 per trade, an imputation over 461 events the ledger dropped, with an interval that
reaches zero.

**Capital basis (not priced in the figures above).** The comparison with the buy-back is
asymmetric in capital. The hedged hold keeps a stock position for a median 3 sessions (90th
percentile 23, maximum about 30) where the buy-back releases margin after one, and the hedge's
peak notional is a median 3.6x m0 (90th percentile 4.4x; 2013-26, N=9,350). Under Reg-T, with
50% on the stock leg and no offset against the short options, peak capital is about
`m0 + 0.5 x 3.6 m0 = 2.8 m0`, so a return of +0.7% of m0 is about +0.25% of peak capital per
trade. Portfolio margin would offset the hedge against the options and lower this. Every forward
figure is reported on both m0 and peak Reg-T capital.

**Hypotheses under test.**

- F-H1 (exit lever, primary). On live fills the hedged hold beats the backtest buy-back basis
  on the same events: mean paired difference `H_live - B_basis` > 0 per trade, unit m0.
- F-H2 (entry start time, primary). A 15:00 resting start beats the current 15:45 ladder start
  on entry credit, measured by random assignment (section 3).
- F-H3 (book level, reported, not a verdict). Mean `H_live` per trade on m0 and on peak capital.

**Success criteria.**

- F-H1 passes if, at 300 completed events, the date-clustered 95% interval on the mean paired
  difference excludes zero. Planning precision: the paired series has sd 5.5% to 6.6% of m0 per
  trade in the backtest; with the section 10 design effect of 2.09, 300 events carry about 144
  independent ones and give a half-width of about +/-1.0%, against an expected +1.7% to +2.8%.
- F-H2 passes if, at 300 completed events (about 150 per arm), the difference in mean entry
  credit over the 15:59 bid between arms, unit m0, has a 95% interval excluding zero. The
  backtest sd of the entry improvement is 2.0% of m0, giving a half-width of about +/-0.65% for
  an expected difference smaller than +0.89% (the 15:45 ladder also rests at the mid).
- F-H3 has no verdict inside a feasible paper horizon. With a per-trade sd of 12% to 13% of m0,
  separating +0.7% from zero needs about 1,200 independent events, about 2,500 trades after the
  design effect, or roughly a dozen quarterly seasons at the 2025-26 rate. The book level leans
  on the backtest; the forward test checks that the two levers survive live execution.
- Futility: at each season end, if the upper bound on F-H1 is below +0.5% of m0, stop the hedged
  hold and revert to the buy-back.

## 2. Exit: the hedged hold

On the reaction session the position is not bought back. Instead:

1. **Counterfactual record.** The 15:59 NBBO of both legs is still recorded (`nbbo_1559`), so
   `B_basis` (buy both legs at the 15:59 asks; a leg with no ask is priced as in section 7) is
   computed for every event exactly as today.
2. **Delta.** At 15:45 ET compute the Black-Scholes delta of the short straddle from the 15:45
   underlying mid, time to expiry ACT/365, and the implied volatility of the straddle's 15:45
   mids; fall back to the entry implied volatility, with reason code `hedge_vol_fallback`.
3. **Hedge order.** Send a market-on-close order for `round(-delta x 100 x contracts) - current
   hedge` shares before the exchange's closing-auction entry cutoff (recalled as 15:50 ET on both
   NYSE and Nasdaq; verify before build). The backtest hedges at the official close with a
   close-based delta, so the 15:45-to-close drift in delta is tracking error, recorded per event.
4. **Daily rebalance.** On every later session until expiry, the 15:20 pass repeats steps 2 and 3
   for every open hedged position. No rebalance band in the first season, to match the backtest.
5. **Expiry.** On the expiry session at 15:45, if `|S - K| / S < 0.5%` (pin zone) the options are
   closed through the ordinary ladder and the hedge unwound at the close, reason `pin_close`.
   Otherwise the options are left to OCC automatic exercise; the hedge then nets against the
   assigned or exercised shares, and any residual stock is sold at the next session's open with
   reason `residual_unwind`. The backtest settles at intrinsic with 5 bp disposal and models
   neither path, so both are reported separately.

## 3. Entry: random start-time assignment

Each admitted event is assigned to arm E0 (current ladder, rung 0 at 15:45) or E1 (rest both legs
at the 15:00 mid, hold until 15:45, then join the current ladder at rung 1). Assignment is by the
parity of the first byte of `sha256(ticker + entry_date)`, fixed before the session and logged,
so it cannot depend on quotes. Arm E1 needs the pass to start by 14:50; the 15:20 confirmation
step (section 5.3) moves to 14:30-14:45 for E1 events, and an event not confirmed by 14:45 drops
to E0 with reason `late_confirm`, which is counted and reported so the arms stay comparable.
Legging rules are unchanged.

## 4. Filters that change

- **Ex-dividend (5.1).** The window extends from the entry date to the expiry date inclusive,
  because the short call is now held to expiry. Expect more skips; the funnel reports them.
- **Expiry before exit (5.2).** Unchanged.
- **Borrow.** When the hedge would be short stock (the short put's delta dominating), the
  underlying must be shortable at the 15:45 check (IB shortable indicator). If not, hold the
  existing hedge, raise an alarm and record `hedge_no_borrow`. Borrow fees above the general
  collateral rate are charged to the event; the backtest charged none.
- **Early assignment.** A short American put deep in the money can be assigned before expiry.
  Assigned shares are treated as part of the hedge from that close, and the event is flagged.

## 5. Order-event log and P&L basis additions

- New event types: `hedge_intent`, `hedge_moc_sent`, `hedge_fill`, `assignment`, `exercise`,
  `residual_unwind`, `pin_close`, each with the same timestamp and identifier fields as section 6.
- Per event: `H_live` (entry credit from fills, hedge fills, settlement or pin-close fills,
  commissions and borrow), `B_basis`, `H_model` (the backtest's hedged hold recomputed from
  official closes on the same contract), the tracking error `H_live - H_model`, the entry arm,
  hold length, peak hedge notional, and peak Reg-T capital.
- Paired figures for F-H1 use every admitted event, filled or not, as section 7 requires; an
  unfilled entry has `H_live = B_basis = 0`.

## 6. Tickets

- T-H1: share orders (market-on-close and marketable limit) in `live/ib_orders.py`, routed
  through the order-event log and the HALT switch, with a per-name share cap in `LiveConfig`.
- T-H2: multi-session position state in the paper book (open hedged positions, current hedge,
  expiry), restored on every pass.
- T-H3: the daily rebalance step and the expiry and pin logic in `live/session.py`.
- T-H4: the 14:30 confirmation path and arm assignment for E1.
- T-H5: assignment and exercise reconciliation against the broker's position report (section 8).
- T-H6: offline tests on a fake gateway: a full hold from entry through expiry with assignment, a
  pin close, a borrow refusal, and a HALT mid-hold that cancels hedge orders without flattening.

## 7. Risks the backtest does not cover

- The hedged hold carries the convexity loss of the reaction gap in full: the backtest's skew is
  -1.6 to -1.9 and the worst 1% of events make half of the total loss. Nothing in this design
  reduces that.
- Closing-auction fills can differ from the official close on thin names; the tracking-error
  series measures it.
- Hedge capital: at the shakedown limit of 5 contracts on 3 names a day with holds up to 30
  sessions, open hedges can stack to several dozen positions; the capital cap in section 4 must
  be checked against peak Reg-T capital, not m0.

## References

Muravyev, D. and Ni, X. (2020). Why do option returns change sign from day to night? Journal of
Financial Economics 136(1), 219-238.

Project records: `outputs/research/2026-11-02-hedged-event-hold/results.json`,
`results_confirm_2025_26.json`, `results_megacap.json`;
`outputs/research/2026-11-02-maker-entry-hedged-hold/results.json`.
