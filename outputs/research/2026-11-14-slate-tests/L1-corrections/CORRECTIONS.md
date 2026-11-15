# Corrections to the hedged-hold valuation: base_corrected.parquet

`base_corrected.parquet` (9,350 rows, one per event of
`outputs/research/2026-11-02-parity-leg-choice/events.parquet`, keyed by ticker and entry_date;
sha256 in `BASE_READY.txt`) re-settles every event of the base panel under four corrections. Built
by `build_base.py` (log `build_base.log`), sized by `score_corrections.py` (log
`score_corrections.log`, figures in `corrections_summary.json`). Every figure below is quoted
from that json.

**Basis of every number.** Per trade, in % of m0 (0.20 times the 15:59 parity forward plus the
15:59 straddle bid), net at the touch: the sale at the 15:59 bid, USD 0.65 per contract per leg,
the stock hedge at its closing half-spread floored at 1 bp (CRSP closing quotes for 2013-24, the
3 bp frozen in amendment 01 for 2025-26). Not annualised. Intervals are 95% percentile intervals
resampling whole reaction-session dates (`protocol.date_clustered_ci`, 5,000 draws, seed 0).
Blocks are by entry year. These are descriptive valuation corrections, not trials of a selector.
The 2019-24 block has already been viewed for this outcome family, so read it as exploratory.
`block_is_clean` returns False for `hedged_event_hold 2025-26` (a `*` row in
`research/ledger/blocks.csv`), so the 2025-26 figures are exploratory too.

## How the panel was rebuilt

Each event is passed through the closed study's own builder,
`research/timing/2026-11-02-hedged-event-hold/study.py::build_event`. It is imported, never
edited. Its `hedged_short_straddle` and `stock_path` names are wrapped in the imported copy, so
the exact inputs it values are recorded. The package function is then called on those inputs
under each correction.

An event enters the panel only if the rebuild gives back the stored `H` (`h_status == "ok"`).
`H_rebuilt` is the old convention on the rebuilt path, and every paired difference below is taken
against it.

| Block | Events | Rebuilt | Not rebuilt | Largest gap to stored H, % of m0 |
|---|---|---|---|---|
| 2013-18 (CRSP) | 2,640 | 2,640 | 0 | 0 |
| 2019-24 (CRSP) | 5,113 | 5,113 | 0 | 0 |
| 2025-26 (Yahoo) | 1,597 | 1,562 | 35 | 0.00085 |

**2025-26 stock paths.** `confirm.py` downloaded its Yahoo bars without saving them, and Yahoo was
not fetched again. Two cached files stand in for them:

- `data/cache/yahoo_adj/adj_close.parquet` (adjusted closes) supplies the total return, the same
  quantity `confirm.py` used.
- `outputs/research/parity_spread/dividends.parquet` (ex-dates 2025-01-06 to 2026-06-26) supplies
  the dividends needed to undo the adjustment.

The as-traded close is rebuilt backwards from the stored settlement close,
`raw[t-1] = adj[t-1] raw[t] / adj[t] + D[t]`, with `D[t]` the cash dividend whose ex-date is `t`.

The reproduction tolerance is 1e-5 of m0. On the 1,562 events that pass, the gaps are at most
8.5e-6: exactly zero on names that pay no dividend, and the rounding of a re-scaled adjusted
series on names that do. The 35 that fail have gaps between 3.4e-4 and 2.6e-2, which is the size
of a dividend missing from the hold.

Of the 35, 25 expire after the dividend file ends. All their `H_*` and component columns are NaN
and `spot_src` is `yahoo_not_rebuilt`. Their stored `H` averages -2.05% of m0 against -0.05% on
the rebuilt events: a difference of -2.0 [-5.2, +0.7], N=35 against 1,562. The interval includes
zero, but the point estimate says dropping them flatters the 2025-26 panel by up to about 0.04%
of m0 per trade (35/1,597 times 2.0%).

`residual_value` does not need the stock path and is filled on all 9,350 rows.

## The corrections

1. **Netting (`H_net`).** The settlement convention adopted on 2026-11-13 (`HEDGED_NET`, trial
   1,856). The assigned share nets against the hedge, so only the residual `h - sign(S - K)`
   trades and nothing is disposed of. The base panel's `H` predates it.
2. **Early call assignment before an ex-dividend date (`H_exdiv`, on top of netting).**
   - When the cum-dividend close is in the money and `D > P(S - D, K, tau)`, the holder
     exercises at that close (`hedged_hold.optimal_call_exercise`). P is the European put at the
     hold's own volatility, evaluated on the ex-dividend open.
   - The writer pays the intrinsic there, and the delivered share nets against the hedge.
   - From that close on, the hedge covers the put alone.
   - Dividends come from CRSP total against price return for 2013-24 (at least USD 0.005) and
     from the cached Yahoo dividends for 2025-26.
3. **The paper book's ex-date skip (`H_skip`).** `H_net` with NaN wherever
   `live/session.py::exdiv_decision` would have skipped: an ex-date in [entry, expiry], or an
   ex-date the source cannot settle. In 2025-26, 172 rows fall outside the dividend file's
   coverage. The rebuild check shows they have no ex-date inside the hedged window, but whether
   one fell between entry and the reaction session is unknown, so they are skipped, as the live
   rule skips an unreadable date.
4. **Financing (`H_fin`, on top of netting).** Per interval between closes, at FRED DFF (ACT/360):
   - a long hedge is charged DFF plus 150 bp;
   - a short hedge is credited DFF less 25 bp of rebate haircut and 25 bp of general-collateral
     borrow;
   - the premium is credited DFF less 50 bp, floored at zero, from entry to settlement;
   - any intrinsic paid early on an assignment is charged the credit rate it forgoes.

   The spreads are declared assumptions in `HoldCorrectionsConfig`. They were recalled from
   IBKR Pro's schedule and not verified at source, because IB's site refuses automated clients.
5. **Declared headline (`H_corr`).** Netting, early call assignment (decided with the rate term
   `K (1 - exp(-r tau))`) and financing.
   - Early exercise of deep in-the-money puts is excluded. Its rule (the European put at DFF
     worth less than intrinsic) overstates how often exercise happens, and the benefit comes
     mostly from releasing the short hedge's borrow.
   - The variant with early put exercise is kept as `H_corr_put`, a sensitivity column.

## Size of each correction, paired, % of m0 per trade

| Correction | 2013-18 | 2019-24 | 2025-26 |
|---|---|---|---|
| Netting, `H_net - H` | +0.219 [+0.210, +0.229] | +0.216 [+0.207, +0.228] | +0.237 [+0.229, +0.244] |
| Early call assignment, `H_exdiv - H_net` | -0.094 [-0.116, -0.072] | -0.078 [-0.100, -0.059] | -0.051 [-0.075, -0.028] |
| Financing, `H_fin - H_net` | -0.076 [-0.083, -0.069] | -0.069 [-0.081, -0.057] | -0.053 [-0.076, -0.032] |
| Early call assignment given financing, `H_corr - H_fin` | -0.088 [-0.110, -0.067] | -0.070 [-0.091, -0.051] | -0.043 [-0.065, -0.022] |
| All but netting, `H_corr - H_net` | -0.165 [-0.190, -0.140] | -0.140 [-0.166, -0.115] | -0.097 [-0.133, -0.063] |
| All, `H_corr - H` | +0.054 [+0.029, +0.080] | +0.077 [+0.050, +0.103] | +0.140 [+0.105, +0.173] |
| Sensitivity: early put exercise, `H_corr_put - H_corr` | +0.036 [+0.016, +0.066] | +0.025 [+0.009, +0.046] | +0.004 [-0.010, +0.020] |
| N (date clusters) | 2,640 (675) | 5,113 (850) | 1,562 (238) |

**The ex-dividend credit, measured.** The hunt summary quoted an upper bound: 2013-18 +0.110%
[+0.088, +0.133] and 2019-24 +0.084% after removing specials. The full revaluation gives -0.094%
[-0.116, -0.072] and -0.078% [-0.100, -0.059], or -0.088% and -0.070% once the exercise condition
includes interest. Both sit inside the bound, so the bound held.

Exercise is optimal on these events:

| Block | Events with an ex-date in the hold | Early call exercise optimal |
|---|---|---|
| 2013-18 | 286 | 124 |
| 2019-24 | 530 | 199 |
| 2025-26 | 128 | 46 |

Two classes are handled separately:

- **Special dividends.** The six events (2 in 2013-18, 4 in 2019-24) are excluded from early
  exercise, because OCC adjusts the strike instead (see A4 in `evidence.md`).
- **Ex-dates on the reaction session.** On 36 events the last cum-dividend day is the entry date,
  where the put still carries event variance. Exercise is optimal on 2 of them. This is not
  modelled, and the bound on its effect is about 0.001% of m0 per trade.

**Netting dominates.** Netting adds about +0.22% of m0 per trade. The two new charges together
remove about 0.10 to 0.17%. The corrected book therefore sits above the stored `H` in every
block, but below the netted `H_net`.

## Corrected headline level, % of m0 per trade

| Block | `H` (rebuilt) | `H_net` | `H_corr` | `H_skip` (N) | Per-trade Sharpe of `H_corr` |
|---|---|---|---|---|---|
| 2013-18 | -1.037 [-1.490, -0.573] | -0.818 [-1.270, -0.354] | **-0.983 [-1.434, -0.523]** | -0.974 [-1.472, -0.482] (2,338) | -0.088 [-0.125, -0.048] |
| 2019-24 | -1.271 [-1.675, -0.872] | -1.054 [-1.455, -0.657] | **-1.194 [-1.591, -0.804]** | -1.093 [-1.521, -0.684] (4,562) | -0.094 [-0.123, -0.065] |
| 2025-26 | -0.053 [-0.862, +0.714] | +0.184 [-0.620, +0.949] | **+0.087 [-0.718, +0.845]** | +0.038 [-0.891, +0.950] (1,256) | +0.007 [-0.054, +0.067] |

`H_corr` components, block means in % of m0, summing to `H_corr` within 2e-16 per event:

| Component | 2013-18 | 2019-24 | 2025-26 |
|---|---|---|---|
| Premium (15:59 bid) | +18.406 | +20.625 | +22.467 |
| Settlement (incl. early assignment) | -19.175 | -21.618 | -21.877 |
| Hedge P&L | +0.103 | +0.086 | -0.214 |
| Equity cost | -0.113 | -0.124 | -0.172 |
| Option fees | -0.107 | -0.077 | -0.057 |
| Disposal (unhedged same-day settlements only) | -0.026 | -0.025 | -0.014 |
| Financing | -0.070 | -0.061 | -0.046 |

**The paper book's skip removes the better events.** Skipped minus kept on `H_net`:

| Block | Skipped minus kept, % of m0 | N skipped |
|---|---|---|
| 2013-18 | +1.36 [+0.21, +2.50] | 302 |
| 2019-24 | +0.36 [-0.80, +1.50] | 551 |
| 2025-26 | +0.74 [-0.59, +2.08] | 306 |

The skipped events are dividend payers. Their residual value is more negative for the seller
(-7.6% against -4.1% of m0 in 2013-18), while their realised `H_net` is higher.

Against skipping, the alternative is to keep every event and price early assignment (`H_exdiv`):

| Block | `H_exdiv`, all events | `H_skip`, surviving events |
|---|---|---|
| 2013-18 | -0.912 | -0.974 |
| 2019-24 | -1.133 | -1.093 |

So skipping does worse than pricing assignment in 2013-18 and better in 2019-24. Neither
difference is outside noise.

## Mean ln(F/K) of the strike sold

The mean ln(F/K) is +2.3 bp (2013-18), +1.5 bp (2019-24) and +3.5 bp (2025-26). This panel's
2025-26 strikes are centred on the forward, so the A1 defect does not reach it.

## Columns

- **Keys and provenance.** `ticker`, `entry_date`, `exit_date`, `expiry`, `block`, `src`,
  `spot_src`, `h_status`, `repro_gap`.
- **Old conventions.** `H` and `B` as stored, and `H_rebuilt`.
- **Corrected outcomes.** `H_net`, `H_exdiv`, `H_skip`, `H_fin`, `H_corr`, `H_corr_put`.
- **Components of `H_corr`.** `c_premium`, `c_settlement`, `c_hedge`, `c_equity_cost`, `c_fees`,
  `c_disposal`, `c_financing`.
- **Residual value.** `residual_value`, with `rv_status`.
- **Flags.** `exdiv_in_hold` (NaN where unknown), `exdiv_on_entry`, `exdiv_on_or_before_reaction`,
  `div_in_hold`, `special_div`, `call_assigned`, `call_assigned_exdiv`,
  `put_assigned_put_variant`, `lnFK`.
- **Entry fields.** `m0`, `strike`, `front_fwd`, `n_hedge`, `permno`.

All outcomes are fractions of m0, so multiply by 100 for the percentages above.
