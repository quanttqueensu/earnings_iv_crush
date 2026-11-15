## What and why

<!-- One or two sentences: what changes and the reason. Link the ROADMAP item. -->

## How it was checked

- [ ] `python -m pytest -q` green
- [ ] `ruff`, `black --check`, `mypy earnings_iv_crush` clean
- [ ] For a study: pre-registration frozen before outcomes, trial recorded in `docs/RESEARCH_STATE.md`
- [ ] For a study: findings note opens with `**Verdict:**` and `**Reproduce:**`; row added to `research/catalogue.csv` and `docs/RESULTS.md` re-rendered
- [ ] Spends a trial? Say how many, and that `research/ledger/trials.csv` has the row
- [ ] Touches the live path (`earnings_iv_crush/live/`, the drivers, `deploy/`)? Name the test that fails against the old behaviour
- [ ] For the paper book: tests on fakes, plus a dry-run log from a real gateway
- [ ] No licensed rows, keys or personal paths in the diff

## Results

<!-- Any number this PR reports, with N, the interval and its basis (per trade, net, cost basis). -->
