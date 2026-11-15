# D0 state

Lane D0, surface builder and benchmark. Trial block 3,132 to 3,141. Complete at 11:32 EST.

## Done

- Step 1: `targets.parquet`, `step1_results.json`, `step1_targets.log`; trial 3,134.
- Step 2: `l4_inputs.parquet`, `l4_scores.parquet`, `step2_results.json`,
  `step2_benchmark.log`; trials 3,132 and 3,133. `TARGETS_READY.txt`.
- Step 3: `earnings_iv_crush/research/chain_surface.py`; `ChainSurfaceConfig` and
  `CHAIN_SURFACE` appended to `earnings_iv_crush/config.py`.
- Step 4: `tests/research/test_chain_surface.py`, 71 pass.
- Step 5: `data/cache/dl/surfaces_2026-11-15.npz` (`build_surfaces.log`), checks
  (`check_surfaces.log`, `check_surfaces.json`), `describe_sparse.log`; trial 3,135.
  `SURFACES_READY.txt`.
- Step 6: full suite 1,910 passed, 2 skipped; mypy clean; D0 files pass ruff and black
  (repo-wide failures are pre-existing, see `diagnosis.log`).
- `evidence.md`, `diagnosis.log`, `scripts_sha256.txt`.

## In progress

Nothing.

## Not started

Nothing in the D0 specification.

## Trial numbers used

3,132, 3,133, 3,134, 3,135. 3,136 to 3,141 unused.
