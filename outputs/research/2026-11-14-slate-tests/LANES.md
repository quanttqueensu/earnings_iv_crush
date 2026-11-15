# Lanes

Idea IDs refer to `outputs/research/2026-11-14-idea-slate/IDEAS.md`.

## L1 corrections (phase 1; folder `L1-corrections/`; trials 2,832 to 2,891)

You may edit `earnings_iv_crush/research/hedged_hold.py` and `earnings_iv_crush/config.py`, with
the Edit tool only, and add `tests/research/test_hedged_hold_corrections.py`. Every later lane
reads your corrected panel, so finish the panel before refinements.

| Idea | Task |
|---|---|
| A1 | Re-strike the 2025-26 ledger at the strike nearest the 15:59 parity forward. Use `data/cache/backfill_chains/` and the logic of `research/frozen_selector/score_oos_2026.py`, imported, never edited. Write `oos_2026_ledger_restrike.csv` with a funnel. Report the old and new mean ln(F/K) and the change in the headline figures, with intervals. |
| A6 | Re-strike the 53aa4898 panel from the backfill chains at 15:59 and re-score its lever. Find the contract source of the 1,779 and 1,780 confirmation (2023-24 flow files). List every panel touched by the defect in `defect_table.csv`, with whether it can be re-struck. |
| A2 | Early call assignment on the last cum-dividend day where D exceeds the put value, as a package function, plus the alternative that skips ex-date holds (the paper book's rule in `earnings_iv_crush/live/session.py::exdiv_decision`). Re-value 2013-24, and 2025-26 with `outputs/research/parity_spread/dividends.parquet`. |
| A3, F2 | Optional financing in the hold: long-hedge interest at FRED DFF plus a declared broker spread, short-hedge rebate less a declared borrow, interest on the premium received, and early exercise of deep in-the-money puts where optimal. Every rate is a named config field with rationale. |
| A4 | Special dividends of USD 12.50 or more inside holds: list them and check the settlement strike against OCC's adjustment rule. |
| A5 | A netted `hedged_short_strangle` in `hedged_hold.py` (residual `h - 1[S>Kc] + 1[S<Kp]`). Re-value 1,819 and 1,826 under `HEDGED_NET`, with the wing-attrition funnel for 1,826 and a test of whether the drops depend on the outcome. |
| A7 | One tracked trial count, written to your folder as `trial_count.csv`; the team lead decides where it lives. Sources: the hash records' `dsr_trial_count`, `research/ledger/trials.csv`, and `docs/RESEARCH_STATE.md` section 1. |

Package changes:

- `hedged_short_straddle` gets an optional `hedge_ratios` override (an array replacing the
  internal Black-Scholes delta) and optional financing inputs. L2 needs the override.
- Defaults reproduce today's output exactly. A test checks this on synthetic paths, and the naked
  case still reconciles to `build_trade`.

Output (the contract for L2, L3 and L4): `L1-corrections/base_corrected.parquet`.

- **Rows.** One row per event of the base panel, keyed by ticker and entry_date.
- **Columns.**
  - `H_net` (netted, as adopted) and `H_exdiv` (with early assignment);
  - `H_skip` (ex-date holds removed, NaN where skipped) and `H_fin` (with financing);
  - `H_corr`, the declared headline: netted, early assignment and financing;
  - each component in % of m0: premium, settlement, hedge P&L, equity cost, fees and disposal;
  - `residual_value` on the project's definition;
  - flags: `exdiv_in_hold`, `special_div`, `spot_src` and `lnFK`.
- **Documentation.** `CORRECTIONS.md` gives each correction's size against `H` (paired mean,
  date-clustered 95%, N) by block.

## L2 execution and cost (phase 2; folder `L2-execution/`; trials 2,892 to 2,951)

Start from `L1-corrections/base_corrected.parquet` and the `hedge_ratios` override.

| Idea | Task |
|---|---|
| B1 | Closing-auction hedging. Replace the half-spread at each hedge close with a declared grid (0, 0.5, 1 bp) plus IB's MOC commission. No auction data exists; label the result assumption-based and give the break-even auction cost. |
| B2 | Minimum-variance delta (Hull and White 2017; verify the citation). Fit the coefficients on 2013-18 reaction-day chains from the backfill cache, apply at the first hedge close through `hedge_ratios` (constant sigma after), and score the paired change in mean H and in its variance. |
| B4 | Capacity of the passing levers. Re-fill the 1,779 resting entry and the 1,819 tight strike against displayed size at 1, 5, 10 and 25 contracts; the rule for size beyond the top of book is declared. |
| B5 | Entry minute by causal spread state inside 15:00 to 15:59, on the 2023-24 flow panels. The 2025-26 contracts are defective. |
| B6 | Per-event expiry choice: the lowest touch per unit of event variance, front against the next expiry at least 7 days out. Use backfill chains; reuse the later-expiry hedged-hold builder (`outputs/research/prereg_2026-11-02-later-expiry-hedged-hold.json` names its study) by import. |
| B8 | Strangle width from the 1,623 move forecast (`outputs/research/prereg_2026-11-12-move-forecast-and-sizing.json`), causal, valued with the netted strangle. |
| B10 | Fee arithmetic: IB tiered against fixed, and resting-order exchange fees and rebates (cite IB's and the exchanges' published schedules, verified). |

## L3 selection and other markets (phase 2; folder `L3-selection/`; trials 2,952 to 3,011)

Selectors are scored on residual value against `matched_random_null`, with strictly causal
features, using `L1-corrections/base_corrected.parquet`.

| Idea | Task |
|---|---|
| C1 | Implied borrow from 15:59 parity: `outputs/research/2026-11-13-alpha-hunt-2/laneB-contract-choice/legs.parquet` (7,619 events, 2013-24), FRED rates, CRSP-inferred dividends. A selector (avoid hard-to-borrow names) and a cost read (what borrow does to the hedge). |
| C3 | First reports after listing, by the earliest CRSP `namedt` (`data/processed/wrds/raw/crsp_a_stock.dsenames.*.parquet`). Print the minimum detectable effect first; run only if it is under 1% of m0, otherwise record as underpowered. |
| C8 | Option-to-stock volume ratio on D-1. Option volume from Alpaca daily bars (`data/cache/alpaca_legacy/options_*_1d.parquet`, strictly prior-day; megacap N about 1,151), stock volume from CRSP where it maps. |
| C2 | FINRA short interest, only if a free, robots-permitted, credential-free source exists. Check and record; do not register for anything. |
| E5 | ForecastEx FES and FNQ daily index contracts against digitals implied by the cached SPY and QQQ 15:59 chains (`data/cache/index_chains/`). Only if a free, permitted fetch of contract-level history exists; `N11-forecastex-event-contracts/data/` lacks those rows. |
| F3 | Same-session concentration cap. A risk read on `base_corrected` (drawdown, worst-session loss, tail share under caps of 3, 5 and 10 events per session), not an edge trial. |

## L4 sequential Bayesian model and trade cards (folder `L4-bayes/`; trials 3,012 to 3,071)

You start during phase 1. Build and test the model on synthetic data first. Read no real outcome
until the team lead tells you `L1-corrections/base_corrected.parquet` is final. Then add
`OnlineBayesConfig` to `earnings_iv_crush/config.py`, with the Edit tool only (L1 is also
editing that file).

**Module.** `earnings_iv_crush/research/online_bayes.py`: a conjugate normal-inverse-gamma
regression updated one trade at a time, using numpy and scipy only.

- **Causal update.** Trade j enters the posterior only on the first entry date strictly after its
  expiry, so no outcome is used before it is known.
- **Forgetting.** A discount factor inflates the coefficient covariance between update dates.
- **Name effect.** A name-level random intercept with causal empirical-Bayes shrinkage, following
  `causal_name_effect` in
  `outputs/research/2026-11-13-alpha-hunt-2/laneJ-name-persistence/lib.py`. Import it or re-derive
  it; do not copy it silently.
- **Reference.** `outputs/research/2026-11-13-alpha-hunt-2/laneD-jump-model/lib.py`, for the
  update mechanics.
- **Predictive.** Student-t.
- **Features.** Six to eight 15:59 cost and structure features, declared in `diagnosis.log`
  before any fit, from `laneE-walk-forward-model/panel.parquet`. Candidates: half_spread,
  implied_move, the term spread, depth_tot, tenor, a megacap flag and log price. Standardised
  with expanding, strictly-prior means and sds.
- **Target.** `H_corr` in % of m0, with `residual_value` as a secondary target.
- **Decision.** Trade if the predictive P(H > 0) exceeds 0.5, declared and not tuned.
- **Book gauge.** The posterior of the intercept through time: P(book mean > 0) and its credible
  interval. This is the sequential monitor F4.

**Tests.** `tests/research/test_online_bayes.py`:

- sequential updates with discount 1 equal the batch conjugate posterior;
- the flat-prior limit matches statsmodels OLS;
- a planted effect on a synthetic book is recovered;
- no trade enters before its expiry, checked by a test that would fail on a leak.

**Scoring.**

- Hyperparameters (prior scales, discount, shrinkage) are fitted on 2013-18 only, then frozen in a
  freeze note.
- Walk-forward on 2019-24, then on 2025-26.
- Primary: log predictive score against a no-feature baseline (intercept and name effect only),
  date-clustered.
- Secondary:
  - calibration (PIT histogram, coverage of 90% predictive intervals);
  - the selected book's mean H against `matched_random_null` on the same dates;
  - the book gauge's path.

**Trade cards.** `trade_cards.parquet` and `trade_cards.csv`, one row for every event, taken or
skipped:

- the 15:59 features;
- the prior predictive mean, sd and P(>0), and the decision;
- the realised decomposition from L1's components;
- the standardised surprise;
- the change in each coefficient's posterior mean caused by that trade's update;
- L1's flags.

Also `trade_cards_summary.md`, covering the twenty largest surprises and what they had in common.
Its numbers come from files only.

**Forward mode.** A `--forward` option reads settled paper trades through
`earnings_iv_crush/live/shadow.py::closed_trades` (read-only, with `Stores.for_mode`) and updates
the frozen posterior. Today there are none, so it must print N=0 and exit non-zero with a clear
message. It never imports anything that can send an order.

## L4 iteration protocol (added 2026-11-15)

The user asked for the model and its parameters to be improved iteratively. That is allowed only
in a way that keeps the held-out reads honest:

1. **Develop on 2013-18 only.** Use rolling-origin evaluation inside it: score each discovery
   year from 2015 to 2018 with the model updated sequentially on everything before it. Iterate
   freely on model class, likelihood (Gaussian or Student-t through a scale mixture), features
   (any 15:59-stamped column of the lane E panel), hierarchical levels (name, industry), target
   (`H_corr` or `residual_value`), discounting and priors. Log every configuration scored, with
   its discovery score, in `search_log.csv`. The count is reported beside the champion.
2. **Freeze once.** Pick one champion and its baseline by the discovery log score alone. Write
   the freeze note, which hashes itself, the scorer and `search_log.csv`. Then read 2019-24 once.
3. **Second round.** After 2019-24 is read, any further change is a second round. Its result is
   reported as exploratory on 2025-26 only, never re-scored on 2019-24, and the lane says so.
   At most two rounds.
4. **Decision rules.** These are declared before the held-out read:
   - P(H > 0) > 0.5;
   - an expected-value rule (trade if the predictive mean exceeds zero);
   - no threshold tuned on held-out data.
5. **Insight deliverables.**
   - `insight.md`: which features carry predictive weight, with posterior means and credible
     intervals, how they drift through time (coefficient paths as a figure), and whether the
     book-level gauge ever crossed P(mean > 0) = 0.5.
   - `trade_cards` for every event.
   - The twenty largest surprises, decomposed by P&L component.
