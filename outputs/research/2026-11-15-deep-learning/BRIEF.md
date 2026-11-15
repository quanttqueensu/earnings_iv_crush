# Deep learning on the 15:59 chain: does the full option surface forecast the hedged hold?

Three lanes and a reviewer. Every lane reads this brief, then its own section in `LANES.md`.

## Hypothesis, scope and success criteria

**Hypothesis.** The 15:59 option chain holds information about the distribution of the hedged
short-straddle outcome that six hand-built summaries do not. The chain means the full smile and
term structure, with spreads and sizes at every strike.

**Benchmark.** The L4 sequential Bayesian model
(`outputs/research/2026-11-14-slate-tests/L4-bayes/`). On 2019-24 it beats its no-feature
baseline by +0.0139 [+0.0080, +0.0195] nats per event (N=5,113, log predictive score,
date-clustered 95%). But its selected book loses -0.55 [-1.01, -0.11] % of m0 per trade.

**The control.** A deep model on L4's own features. It tells "more information" apart from "more
flexibility".

**Prior: low.**

- Tabular deep learning on a few thousand rows rarely beats a linear or tree model (Grinsztajn,
  Oyallon and Varoquaux, NeurIPS 2022, recalled).
- The 375-model zoo and the lane E walk-forward model both failed.
- The closest published work is Kelly, Kuznetsov, Malamud and Xu, "Deep learning from implied
  volatility surfaces" (working paper, recalled). It applies a CNN to IV surface images to
  predict returns. This test differs: the event is scheduled, the target is a hedged short
  straddle net of cost, and the output is a full predictive distribution.

**Success criteria, declared before any fit.**

1. **Forecaster pass.** On 2019-24, the per-event log predictive density of `H_net` beats the L4
   champion's (re-run on `H_net` by D0). The mean gain has a date-clustered 95% interval
   (`protocol.date_clustered_ci`) that excludes zero, and the gain is positive in at least 4 of
   the 6 years.
2. **Economic pass.** The selected book must beat both comparators:
   - the tight-spread-per-date screen, taking the same number of events per date;
   - `matched_random_null`.

   This holds on `H_net` and on `residual_value`, each with date-clustered intervals. The rule is
   in "The decision rule" below.
3. **Mechanism check.** Any pass is decomposed by channel occlusion and by the overlap with the
   tight-spread screen. A lift carried by the spread or size channels is the known spread effect,
   and is reported as that.

A forecaster pass without an economic pass is reported as exactly that, and is not spun.

## Read before anything else

- **Rules.** `CLAUDE.md` and `CLAUDE.local.md` (rules, landmines).
- **The previous programme.**
  - `outputs/research/2026-11-14-slate-tests/BRIEF.md`: "Rules for this programme" (1 to 5) and
    "Resume and checkpoint rules" (1 to 5) apply here unchanged, with this folder and its trial
    block substituted.
  - `outputs/research/2026-11-14-slate-tests/SUMMARY.md`: every review correction listed there
    is a failure here. Three new failure classes:
    - a baseline that omits a fee the treatment pays;
    - a decision threshold on a Monte Carlo mean of a quantity with no finite mean;
    - log timestamps that are not a clock, and scripts edited after their run.
- **L4's files.** `outputs/research/2026-11-14-slate-tests/L4-bayes/insight.md`, `l4lib.py` and
  `decompose_selection.py`. The last holds the tight-spread-per-date comparator; import it or
  reproduce it exactly.
- **Package code.** `earnings_iv_crush/research/online_bayes.py` (`yj`, `yj_inv`, `yj_logderiv`,
  `run_online`, `causal_standardise`), `earnings_iv_crush/research/protocol.py` and
  `earnings_iv_crush/config.py` (`ONLINE_BAYES_L4_MODEL`, `ONLINE_BAYES_L4_BASELINE`).

## Data (verify before building on it)

- **Target base.** `outputs/research/2026-11-14-slate-tests/L1-corrections/base_corrected.parquet`:
  9,350 events, 2013-04 to 2026-08. `H_corr` is stored as a fraction of m0 per trade; check the
  units of `residual_value` before using it. There is a `block` column.
- **Commission.** `outputs/research/2026-11-14-slate-tests/L2-execution/hedge_commission.parquet`:
  `comm_1c` as a fraction of m0. It is IB Tiered pricing, recalled, not verified.
- **Chains.** `data/cache/backfill_chains/{ticker}_{entry_date}.parquet` exists for all 9,350
  events. These are Databento MBP-1 rows; anything derived from them stays under
  `data/cache/dl/` (gitignored) and never enters a markdown file or a figure's data.
- **Features.** `outputs/research/2026-11-13-alpha-hunt-2/laneE-walk-forward-model/panel.parquet`,
  stamped 15:59, joined one-to-one on ticker and entry_date.
- **L4 output.** L4's per-event predictive output is in `L4-bayes/run_H_corr.parquet`. It is fit
  on `H_corr`, not `H_net`, so it is not the benchmark here; D0's re-run is.

## Declarations every lane uses

- **Target.** `H_net = H_corr - comm_1c`, net at the touch, not annualised.
  - Units: both columns are stored as fractions of m0 per trade, which the team lead checked.
    The 2019-24 means are -0.011941 and 0.001398. Report in % of m0.
  - Coverage: 35 of the 9,350 events have no `comm_1c` row. They are dropped with a funnel
    line, and D0 tests whether the drops depend on the outcome.
  - D0 writes `targets.parquet`; no package default changes.
- **Primary statistic.** The log predictive density of `H_net` per event, in the `H_net` space,
  identical for every model. A model fitted on a transformed target adds the Jacobian
  (`online_bayes.yj_logderiv`).
- **The finite-mean rule.**
  - L4 models z = yj(-H/U) with Student-t errors. Any Student-t in z, of any degrees of freedom,
    has an infinite mean in `H` space, because `yj_inv` grows exponentially on the loss side.
    That is why L4's mean is minus infinity.
  - A network head is eligible for the economic rule only if its predictive mean of `H_net` is
    finite. In practice that means a Gaussian or Gaussian-mixture head in z, or any head fitted
    directly on `H_net` with finite mean.
  - The mean is computed by deterministic quadrature, never by Monte Carlo.
  - Heavy-tailed z heads may compete on the log score, but cannot drive the economic rule.
- **The decision rule.** Trade if the predictive mean of `H_net` is above 0. This is declared,
  not tuned.
- **Blocks.**
  - Development folds take a rolling origin: for Y in 2016, 2017 and 2018, train on events whose
    expiry is before 1 January of Y, and score the events entered in Y.
  - Early stopping uses the last calendar year of the training window, never the scored year.
  - The held-out read is 2019-24, once per frozen configuration. It walks forward with refits at
    each quarter start, on events whose expiry is before that quarter start.
  - 2025-26 is exploratory, read after 2019-24.
- **Asymmetry against L4 (invariant 2).** L4 updates after every expiry, while a network refits
  quarterly. The network is therefore at a staleness disadvantage, which goes in every
  comparison table.
- **Causality.**
  - Surfaces use quotes at or before 15:59 ET on the entry date only.
  - Standardisation, normalisation and any clipping are fit on the training rows of each fold.
- **Search budget.** D1 has 40 configurations and D2 has 24. Every configuration goes to
  `search_log.csv`, one row each, with its fold scores. Search with 2 seeds; the frozen
  configuration runs as a 5-seed ensemble (averaged mixture densities), with seed dispersion
  reported.
- **Freeze.**
  - Before the held-out read, write `freeze_<lane>.md`. It records the configuration and a
    sha256 of the scorer script, the model code, the frozen configuration JSON and the
    development `search_log.csv`, and it hashes itself.
  - The held-out scorer refuses to run if those hashes differ.
  - Never edit a script after it produced a result without re-running it.
  - Log every block view in `blocks_viewed.csv` at read time, with a UTC clock timestamp taken
    when the data is loaded.

## Environment

- **Deep-learning code** runs in `C:\Users\jodor\.venvs\ivcrush-dl`: Python 3.12.4, torch
  2.5.1+cu124 on an RTX 4060 Laptop GPU with 8 GB, and the main environment's numpy, pandas and
  scipy versions. Call it as:

  ```bash
  cd C:/Users/jodor/Documents/QUANTT_IVCrush_Project
  PYTHONPATH=. PYTHONIOENCODING=utf-8 C:/Users/jodor/.venvs/ivcrush-dl/Scripts/python.exe <script>
  ```

- **Package code and its tests** must still pass in the main Python 3.14 environment
  (`python -m pytest`, `ruff`, `black`, `mypy`). Torch-dependent tests use
  `pytest.importorskip("torch")`.
- **Torch code stays out of the package.** It lives in the lane folder; package modules stay
  numpy-only.
- **Seeds.** Set torch, numpy and CUDA seeds, and use `torch.use_deterministic_algorithms(True,
  warn_only=True)`.
- **Never install anything.** If a package is missing, stop and report it.

## Trial numbers

Take trial numbers only from your block in `RESERVED_TRIAL_IDS.md`. A held-out read of a frozen
configuration is one trial, and so is each economic rule scored. Development fits are charged
through `search_log.csv`, not as trials.

## Deliverables (in your lane folder)

- `evidence.md`, the dossier;
- `trials.csv` (trial_id, idea, rule, block, N, statistic, interval, verdict);
- `diagnosis.log`, `STATE.md` and `blocks_viewed.csv`;
- freeze notes, scripts, logs and the per-event output parquet.

No `report.md` or `findings.md`. The findings are the analyst's. British spelling, no em dashes.

## Your final message

Under 600 words, verdict first:

- each result with N, interval and basis;
- the search count;
- the package changes and tests, with their status;
- what you could not verify.
