# Contributing

How work gets from an idea to `main`. The research rules are [`docs/PROTOCOL.md`](docs/PROTOCOL.md);
this file covers the mechanics.

## Before you start

1. Run `python -m pytest -q` and `python -m earnings_iv_crush.ops.orient` on a fresh clone.
2. Read [`docs/SYSTEM.md`](docs/SYSTEM.md) and [`docs/RESEARCH_STATE.md`](docs/RESEARCH_STATE.md).
3. Reproduce one recorded number end to end before changing anything: `python
   scripts/validate_screen.py` after `sync pull` (see [`docs/DATA.md`](docs/DATA.md)). It teaches
   the harness and proves your environment.

## Branches and pull requests

- `main` is protected: changes arrive by pull request, and CI (ruff, black, mypy, pytest) must be
  green before merge.
- Branch from `main` with a short descriptive name (`study/exit-only-maker`,
  `book/reconcile-job`). Keep branches short-lived; rebase on `main` rather than merging it in.
- Stage files explicitly (`git add path/to/file`), never `git add -A` or `git add .`: the working
  tree holds caches and outputs that must not ship.
- One logical change per pull request. Fill in the template; say what you ran and what it printed.
- A study's pull request carries its findings note, its row in `research/catalogue.csv` and the
  re-rendered `docs/RESULTS.md` (`python -m earnings_iv_crush.ops.catalogue`); CI fails if the
  page is stale or a study has no row.
- Paths with a code owner (the paper book, `config.py`, `frozen.py`, the drivers, any
  pre-registration) need the owner's review. See `.github/CODEOWNERS`.

## Code standard

- Python 3.10+, `from __future__ import annotations`, full type hints.
- Every parameter is a named field in `earnings_iv_crush/config.py` (frozen dataclass, rationale
  in the docstring) or a named constant at the top of a study; no magic numbers.
- NumPy-style docstrings on public functions; module docstrings name the file and its purpose,
  and modules carrying maths end with References.
- black and ruff at line length 100, mypy clean on the package:
  ```bash
  python -m ruff check . && python -m black --check . && python -m mypy earnings_iv_crush
  ```
- Tests sit beside the change, run offline on synthetic data, and check against an independent
  reference where one exists. A test that guards a past defect names it in its docstring.
- Comments explain constraints and reasons, never what the diff did.
- A gate, filter or join that can silently produce an empty or degenerate result raises, warns or
  prints a funnel.

## Data and secrets

- Credentials only in `.env` (git-ignored). Never paste a key into code, a commit, an issue or a
  chat; if one is exposed, rotate it.
- No licensed vendor rows in any commit ([`docs/decisions/0004`](docs/decisions/0004-licensed-data-stays-out-of-git.md)).
- Metered pulls need an estimate, a hard `--cap` and the team lead's go-ahead first.

## The paper book

Nothing that can send, modify or cancel an order runs without the team lead asking for it.
Changes to `earnings_iv_crush/live/` or the drivers come with tests on fake gateways and a dry-run
log from a real gateway in the pull request. Never create `_private/TRANSMIT_OK` yourself.

## Work logs

At the end of a working session, add a short entry to `work-logs/<your-handle>/YYYY-MM.md`
(in Claude Code, `/log-work` gathers the evidence). The update is written by you, in your words.
