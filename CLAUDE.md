# Earnings IV Crush: rules for agents

Earnings-event volatility research on single-name US options, and an Interactive Brokers paper
book that trades the rule every session. This file holds the rules, which do not rot. It holds no
figures about results, which do: those live in `docs/`, and live state comes from a command.

Start every session with:

```bash
python -m earnings_iv_crush.ops.orient     # repo, data, switches, paper book, research counts
```

Then `docs/SYSTEM.md` (what we trade, what we know, what is decided) and `docs/RESEARCH_STATE.md`
(the closed list). `docs/INDEX.md` says which file owns any other question.

| You want | Ask |
|---|---|
| Any number about the paper book, the data present or the trial count | `orient` (a section that cannot measure says `UNMEASURED`) |
| Whether an idea has been tried | `docs/RESEARCH_STATE.md`, or `/graveyard` |
| A figure to quote | its findings file under `research/<line>/findings/`, never memory |
| How to run a study | `docs/PROTOCOL.md`, `research/README.md`, `/new-study` |
| How the paper book runs and what an alarm means | `docs/RUNBOOK.md` |

## Hard rules: the order path

Not all enforced by a hook. Treat them as absolute anyway: each names an action that cannot be
undone.

1. **Never transmit on your own initiative.** Anything that can send, modify or cancel an order
   at the broker (`scripts/paper_trade_ibkr.py session --transmit`, `forward-exit --transmit`,
   anything in `earnings_iv_crush/live/` called with a connected gateway) runs only when the team
   lead has asked for it in this session. Even then, show the concrete order list from a dry run
   and get an explicit go first.
2. **Never create or delete `_private/TRANSMIT_OK`, and never remove `outputs/live/HALT` or
   `outputs/live/STOP`** unless the team lead asks in the session.
3. **Paper only.** Never edit `LiveConfig.ib_live_ports`, the port guard in `ib_connection.py`, or
   anything that would let the harness reach a live account.
4. **The logs are records.** Never edit `outputs/live/order_events.csv`, `intended_trades.csv`, the
   open-positions store or the forward ledgers by hand. A correction is a new, dated row with a
   reason.
5. **Never print, copy or transmit credentials.** `.env` is denied to agents. To check a key is
   set, print the boolean, never the value.

## Hard rules: research

- **Read the closed list before proposing anything**, and name the nearest closed study and the
  closest published work (`docs/REFERENCES.md`) with how the idea differs.
- **Pre-register and freeze before any outcome exists** (`/prereg`). Scorers call
  `protocol.verify_prereg` first. **Never edit a file under `research/*/preregs/`**: those texts
  are hashed; a change is a new dated amendment file with its own hash.
- **Closed studies are frozen.** Do not edit the logic of a module in `research/<line>/`; start
  new work from `research/_template/` and import package code instead of copying it.
- **Causal everything**: thresholds and features at an event use strictly earlier events only.
- **Score selectors on residual value**, benchmark them against the participation-matched random
  null, and report date-clustered intervals (`earnings_iv_crush/research/protocol.py`).
- **Per-trade Sharpe is the primary statistic.** Annualise only by the square root of the book's
  own trades per year and say so; never by the daily square root of 252 on an event book.
- **State the basis of every scaled number** beside it: per trade or per year, per side or round
  trip, gross or net, at the mid or at the touch, on margin or on premium.
- **Never quote a figure listed in `docs/RESEARCH_STATE.md` section 4.**
- **Report attrition** with a funnel and test whether the drops depend on the outcome.
- **Never use Alpaca end-of-day features for selection**: they leak relative to a 15:59 decision.
- **Label every result synthetic or real**, and never let a synthetic or unverified number set
  direction.
- **Findings are the analyst's.** An agent may gather evidence and draft structure; the analyst
  who ran the study writes and signs the verdict.

## Hard rules: data

- No licensed vendor rows (Databento, WRDS) in any commit, findings note, figure data or message
  outside the team. Aggregates the project computed are fine.
- **Metered pulls**: price the request with the vendor's free cost call, pass a hard `--cap`,
  get the team lead's explicit go-ahead in the session, and reconcile actual against estimate
  afterwards. Every builder under `scripts/build/` may spend money; check its docstring.

## Hard rules: code

- `earnings_iv_crush/config.py` is the single source of truth: frozen dataclasses, every number
  named with its rationale. No magic numbers in modules.
- **No silent fallbacks.** A gate, join, filter or default that can produce an empty, NaN or
  degenerate result raises, warns or prints a funnel. Never `except: pass`, never `fillna` with an
  invented value.
- **One valuation path.** Any new estimator reconciles to `engine/pnl.py::build_trade` on the
  same events before it is trusted.
- Tests run offline on synthetic data or fakes; never connect to a broker or a paid source in a
  test. Live-path changes come with fake-gateway tests.
- black and ruff at line length 100, mypy clean on the package, suite green before calling work
  done. On Windows set `PYTHONIOENCODING=utf-8` and call tools as `python -m pytest|ruff|black|mypy`.
- Entry points run from the repository root (`python -m scripts.paper_trade_ibkr`,
  `python research/<line>/<study>.py`).

## Git

- Never push, force-push, merge, rebase a shared branch or rewrite history unless asked.
- Stage files explicitly; never `git add -A` or `git add .`.
- Plain commit messages in the author's voice. No co-author or tool attribution lines.
- Work on a branch and open a pull request; `main` is protected.

## Writing

British spelling. Commas or full stops, not em dashes. Finished prose, no filler. Every number
carries N, its interval and its basis.

## Landmines

Each of these has produced a figure the project had to withdraw.

- The daily square root of 252 applied to a book that trades a few dozen times a year.
- A ledger that drops events whose exit leg has no bid: those follow large moves, so the
  survivors flatter the book.
- DoltHub snapshots are sparse and rotate expiries; a default lookback can pair an event's entry
  chain with itself as the exit chain.
- The megacap entry spot falls back one session silently on a minority of events; use the
  repaired file for any new megacap result.
- Run dates in UTC: an evening run books tomorrow's date. Use `exchange_today`.
- Weekday arithmetic is not the exchange calendar; check brackets around market holidays.
- IB without a real-time subscription serves quotes about fifteen minutes late; fills on them are
  not evidence.
- Calendar sources disagree on dates and sessions; the paper book trades only on two of three.
- A one-sided quote never becomes a mid.

## The desk

`.claude/README.md` maps the skills, agents, hooks and path-scoped rules this repository ships.
