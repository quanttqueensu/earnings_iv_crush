# Lanes

All paths are relative to the repository root. `<base>` is
`outputs/research/2026-11-15-deep-learning/`.

## D0, surface builder and benchmark (`<base>D0-surface/`; main environment)

D0 owns every input the other lanes read. Do the steps in this order and write each marker the
moment its files are complete, because D1 and D2 are waiting on them.

### Step 1: targets

Write `<base>D0-surface/targets.parquet`, one row per event, with the columns ticker,
entry_date, expiry, block, H_corr, comm_1c, H_net and residual_value. Add the premium unit `U`
exactly as `L4-bayes/l4lib.py::target` builds it for `H_corr`, with `H_net` in its place.

Then:

- print the funnel;
- test whether the 35 events without commission differ in `H_corr`, with a Welch t and a
  date-clustered interval on the difference;
- never fill a missing value.

### Step 2: the L4 benchmark on `H_net` (trials 3,132 and 3,133)

- **Run.** Re-run `online_bayes.run_online` with `ONLINE_BAYES_L4_MODEL` and
  `ONLINE_BAYES_L4_BASELINE` on `H_net`, through the same design as `l4lib.py`. Import it; do not
  edit it.
- **Two outputs:**
  - `l4_inputs.parquet`: keys plus the prior predictive quantities only, with no
    outcome-derived column. That is loc, scale, df, the name effect at entry and the number
    settled at entry, both in z space and as described in `run_online`'s output. D1 and D2 may
    use these as causal inputs on every row.
  - `l4_scores.parquet`: keys plus the per-event log score in `H_net` space (with the Jacobian),
    PIT and covered, for the model and the baseline. D1 and D2 may read rows with entry year
    2018 or earlier during development. They read later rows only inside their frozen held-out
    scorer.
- **Report** the 2019-24 log-score gain of the model over the baseline, against the slate-tests
  figure on `H_corr` (+0.0139 [+0.0080, +0.0195]).
- Write `TARGETS_READY.txt`.

### Step 3: the surface module

- **Module.** New `earnings_iv_crush/research/chain_surface.py` (numpy and pandas only), with
  `ChainSurfaceConfig` added to `config.py` by the Edit tool, every number named with its
  rationale.
- **Snapshot.** Use exactly the 15:59 snapshot rule the base was built with: find it in
  `outputs/research/2026-11-14-slate-tests/L1-corrections/build_base.py` or `a6_restrike.py` and
  verify it. Parse OCC symbols as `research/chains.py::_parse_chain` does.
- **Expiries.** Use the event's front expiry (base `expiry`) and the next listed expiry after it.
- **Forward and time.**
  - The front forward is base `front_fwd`.
  - The next expiry's forward is the median put-call parity forward from the 5 strikes nearest
    it, with FRED DFF from `outputs/research/2026-11-13-alpha-hunt/lane1-macro/dl/`.
  - Time is ACT/365 from 15:59 ET on the entry date to 16:00 ET at expiry.
- **IV.** Invert Black-76 IV on bid, ask and mid. Mid IV exists only where bid > 0 and ask > 0,
  since a one-sided quote never becomes a mid. A vectorised inverter is allowed, tested against
  `research/hedged_hold.py::option_iv`.
- **Grid.** Standardised moneyness x = ln(K/F) / (sigma_atm sqrt(tau)), at 9 points from -2 to
  +2, for each expiry. sigma_atm is that expiry's ATM mid IV.
  - This deviates from the plan's +/-0.20 raw log-moneyness. The reason is that implied moves
    differ about tenfold across names, so a raw grid would be mostly empty for megacaps and
    truncated for small caps.
  - Interpolate linearly in x between quoted strikes, with no extrapolation.
- **Channels at each point.** Call and put mid IV divided by sigma_atm; call and put relative
  spread (ask - bid) / mid; log1p of bid and ask size for calls and puts; and a validity mask.
- **Scalars.** sigma_atm front and next, tau front and next, front_fwd, and m0.

### Step 4: tests

Write `tests/research/test_chain_surface.py`, offline and synthetic. It checks:

- Black-76 prices invert to the planted IV over a grid;
- a flat smile interpolates exactly;
- quotes after 15:59 are excluded;
- missing strikes set the mask;
- a one-sided quote gives no mid IV;
- parity recovers a planted forward.

### Step 5: build and checks

- **Build.** Write `<base>D0-surface/build_surfaces.py`, parallel over files, writing
  incrementally to `data/cache/dl/surfaces_2026-11-15.npz` (events x channels x 2 x 9, plus keys
  and scalars). Anything derived from Databento rows stays under `data/cache/dl/`.
- **Funnel.** Print: events, file present, front expiry found, next expiry found, grid fill rate
  by block, and all-mask events.
- **Reconciliation.** Front ATM mid IV and half-spread recovered from the surface against the
  laneE panel features, with the tolerance stated.
- **Spot checks.** Hand-check 5 events against the raw file.
- **Attrition.** Test whether sparse surfaces (fill below 50%) depend on the outcome.
- Write `SURFACES_READY.txt`, listing the file path, its sha256 and the channel order.

### Step 6: verification

Run `python -m pytest`, `ruff`, `black` and `mypy earnings_iv_crush`, all clean in the main
environment.

## D1, surface network (`<base>D1-surface-net/`; venv)

- **Until `SURFACES_READY.txt` exists**, build and test on synthetic data only:
  - the model code;
  - the heads, a Gaussian mixture in z (K from 1 to 3) and a Student-t in z for log score only;
  - the Jacobian, the quadrature mean and the fold runner;
  - `tests/research/test_dl_heads.py`, with `importorskip("torch")`. The densities integrate to
    1, the Jacobian matches a finite difference, the quadrature mean matches a closed form for
    K=1 Gaussian with k=0, and a planted surface effect is recovered.

  Then read the surfaces, `targets.parquet` and `l4_inputs.parquet`.
- **Inputs.** The surface tensor, with masked points zeroed after normalisation and the mask
  kept as a channel, plus the scalars and L4's seven standardised features.
- **Architectures searched.** An MLP on the flattened surface, and a 1-D convolution over
  moneyness with expiry and channel as input channels. Under 50k parameters.
- **D1a, surface plus scalars.**
- **D1b, boosting from L4.**
  - The head's z location is L4 loc plus a network offset, and its log scale is L4 log scale
    plus a network offset. Both are initialised at zero, so D1b starts at a Gaussian version of
    L4.
  - D1b answers the question that matters: does the chain add information beyond L4?
- **Scoring and comparators.**
  - Score against `l4_scores.parquet` for each fold.
  - The selected-book comparators are the unconditional book, the tight-spread-per-date screen
    at matched participation, and `matched_random_null`. All use date-clustered intervals, on
    `H_net` and `residual_value`.
- **Occlusion on a pass.** Zero the IV channels, then the spread channels, then the size
  channels, and report the change in log score.
- **Output.** `cards.parquet`, keyed as the L4 cards: predictive mean (quadrature), sd, P(>0),
  log score and decision.

## D2, tabular control (`<base>D2-tabular/`; venv)

- **Model.** A mixture-density MLP with Gaussian mixture components in z (K from 1 to 3), plus a
  Student-t variant for log score only.
- **Inputs.** L4's seven features, causally standardised, plus L4's causal name effect at entry
  from `l4_inputs.parquet`. No surface.
- **Until `TARGETS_READY.txt` exists**, build and test on synthetic data. You may import the head
  and Jacobian code from D1's folder once its tests pass; otherwise write your own and say so.
- **Same blocks, scoring, comparators and freeze rules as D1.**
- **The reading.**
  - If D2 ties L4 and D1b beats it, the gain is information.
  - If D2 also beats L4, the gain may be flexibility.
  - Report both against L4 and against each other on the same events.

## Review (`<base>review/`; quant-reviewer, after D1 and D2 finish)

The reviewer gets the files, not the conclusions, and checks:

- the freeze notes predate the held-out logs (file times and `blocks_viewed.csv` clock stamps);
- the hashes reproduce;
- no quote after 15:59 enters a surface;
- no training row has an expiry on or after its refit date;
- normalisation is fit on training rows only;
- the Jacobian and quadrature mean, by independent numeric integration of one event's density;
- every number in each `evidence.md` traces to a file;
- the search counts match `search_log.csv`.
