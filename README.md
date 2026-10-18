# Earnings IV Crush

[![CI](https://github.com/quanttqueensu/earnings_iv_crush/actions/workflows/ci.yml/badge.svg)](https://github.com/quanttqueensu/earnings_iv_crush/actions/workflows/ci.yml)

Earnings-event volatility research for the QUANTT IV-crush team. Implied volatility on
single-name US options rises into a scheduled earnings announcement and collapses once the
number is public: it falls on 98.1% of 989 measured events. The project asks whether that crush
can be captured after real trading costs, and it has built the machinery to answer properly:
quote-marked OPRA option data back to 2013, measured execution costs, a pre-registration and
trial-counting protocol, and an Interactive Brokers paper book that trades the rule through a
mid-to-touch order ladder every session.

The short answer so far is that the premium is visible at the mid and a liquidity taker pays it
away. [`docs/SYSTEM.md`](docs/SYSTEM.md) has the evidence; [`docs/ROADMAP.md`](docs/ROADMAP.md)
has what is open.

## Start here

| If you want | Read |
|---|---|
| What we trade, what we know, what is decided | [`docs/SYSTEM.md`](docs/SYSTEM.md) |
| What has already been tried (read before proposing anything) | [`docs/RESEARCH_STATE.md`](docs/RESEARCH_STATE.md) |
| What to work on | [`docs/ROADMAP.md`](docs/ROADMAP.md) |
| How a study is run | [`docs/PROTOCOL.md`](docs/PROTOCOL.md), [`research/README.md`](research/README.md) |
| How to contribute | [`CONTRIBUTING.md`](CONTRIBUTING.md) |
| Which file owns any other question | [`docs/INDEX.md`](docs/INDEX.md) |

Working with Claude Code: the repository ships its configuration. [`CLAUDE.md`](CLAUDE.md) holds
the rules an agent works under and [`.claude/README.md`](.claude/README.md) maps the skills,
agents and hooks. Run `/orient` at the start of a session.

## Getting started

Python 3.10 or later.

```bash
git clone https://github.com/quanttqueensu/earnings_iv_crush.git
cd earnings_iv_crush
python -m venv .venv
source .venv/bin/activate              # Windows: .venv\Scripts\activate
pip install -e ".[dev]"

python -m pytest -q                    # offline, synthetic data; must be green
python scripts/demo_pipeline.py        # the whole valuation and scoring path on synthetic events
python -m earnings_iv_crush.ops.orient # measured state: repo, data, paper book, research
```

The demo prices a synthetic panel through the same valuation, cost model and reporting contract
every real result uses. Its generator prices announcement risk fairly, so the gross book is near
zero and the gap to the net book is the cost stack; it is a wiring check, labelled as such.

**Real numbers need the research caches**, which are licensed and so never in git. Copy
`.env.example` to `.env`, add the bucket keys from the team lead, then:

```bash
python -m earnings_iv_crush.data.sync pull   # hash-checked against data/MANIFEST.pin.json
python scripts/validate_screen.py            # must reproduce N=391, per-trade Sharpe +0.055992
```

Sources, licences and costs are in [`docs/DATA.md`](docs/DATA.md).

## Layout

| Path | What it holds |
|---|---|
| `earnings_iv_crush/` | The package: `data/`, `engine/`, `strategy/`, `baseline/`, `research/` (shared research infrastructure), `live/` (the paper book), `ops/`, `config.py`, `frozen.py` |
| `scripts/` | Stable entry points: the demo, the research run, the paper book, reports; `scripts/build/` holds the data builders |
| `research/` | Closed studies by line, each with its pre-registrations and findings; `_template/` for new ones |
| `tests/` | The suite, offline |
| `docs/` | The documents, one owner per question |
| `deploy/` | The cloud host for the paper book |
| `.claude/`, `CLAUDE.md` | The Claude Code configuration |

Code structure in detail: [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md).

## The paper book

`python -m scripts.paper_trade_ibkr session` runs one session against an IB **paper** account:
two-of-three calendar confirmation, exits on the stored contracts, entries admitted in a fixed
hash order, one mid-to-touch ladder from 15:45 to 15:55 ET, a hard cancel at 15:58, and booking
from broker fills. It is a dry run unless explicitly told to transmit, it refuses every
live-account port, and every order event is logged before it is acted on. Operating it:
[`docs/RUNBOOK.md`](docs/RUNBOOK.md). Its rules: [`docs/FORWARD_TEST_SPEC.md`](docs/FORWARD_TEST_SPEC.md).

## Glossary

| Term | Meaning |
| --- | --- |
| **At-the-money (ATM)** | The option whose strike price is closest to where the stock is currently trading. |
| **Straddle** | A call and a put on the same stock, same strike, same expiry. Selling one profits if the stock stays still. |
| **Implied volatility (IV)** | The amount of future movement an option's price implies the market expects, quoted as an annualised percentage. |
| **Implied move** | How far the option market expects the stock to move over the announcement, in percent, read off the straddle price. |
| **Term structure / term spread** | How implied volatility differs across expiry dates. The spread used here is front-week IV minus back-month IV. |
| **Hit rate** | The share of trades that made money. It says nothing about size, so a high hit rate with a few large losses can still lose overall. |
| **Premium** | The cash received for selling the options. |
| **Return on margin (RoM)** | Profit divided by the capital a broker requires to hold the position. The project's standard denominator, because it is what actually ties up money. |
| **Reg-T margin** | The US regulatory margin formula, approximated here as 20% of the stock price plus the premium received. |
| **Gross vs net** | Gross is before trading costs. Net is after the bid/ask spread and commissions. On short-dated options the gap between the two is large. |
| **Mid, touch, half-spread** | The mid is the midpoint of the bid and ask. Paying the touch means buying at the ask or selling at the bid. The half-spread is the distance from mid to either side, and is what a trade costs if it crosses. |
| **Sharpe ratio** | Average return divided by the standard deviation of returns: how much return was earned per unit of variability. Higher is better; roughly 1.0 is generally considered good for a live strategy. |
| **Per-trade vs annualised Sharpe** | Per-trade Sharpe uses one trade as the unit. Annualising any Sharpe means multiplying by the square root of the observations in a year, with the period matching the series it was computed on (Lo, 2002). For a trade-unit series that is the square root of trades per year, derived from the data rather than fixed; √252 is the daily figure and would inflate a book like this more than threefold. See docs/PROTOCOL.md rule P8. |
| **Date-clustered 95% interval** | The range the true result plausibly sits in. It is clustered because many earnings land on the same day and are not independent observations, which a naive interval would ignore. An interval containing zero means the result cannot be distinguished from no edge. |
| **Deflated Sharpe** | A Sharpe ratio adjusted for how many configurations were tested before finding it. It answers the question "would a strategy this good have shown up anyway, by chance, given how much we searched?" |
| **In-sample, out-of-sample, holdout** | In-sample data is what the strategy was designed on. Out-of-sample data is what it was not. A holdout is data deliberately withheld until the rules were frozen, and it is the only honest test. |
| **Participation-matched random selector** | A benchmark that picks the same number of events, from the same pool, at random. It is the fair comparison for a selection rule, because it holds everything fixed except the rule itself. |
| **Vega, theta, spot** | The three sources of profit and loss here. Vega is sensitivity to implied volatility, theta is the value lost to time passing, spot is sensitivity to the stock price itself. |
| **Pre-registration** | Writing down the hypothesis, the exact test and the criterion for calling it a failure, before running it. It is what stops a result being reinterpreted after the fact. |
| **Residual value** | The part of a short straddle's P&L left after the premium collected and the gap cost: what the option was still worth at exit relative to what it was sold for. Selection work is scored on it because realised P&L rewards simply selling bigger options. |
| **Liquidity taker / provider** | A taker crosses the spread to trade now; a provider rests a limit order and waits to be filled. Every taker version of this trade fails net; the paper book tests how much a mid-seeking ladder recovers. |
| **Markout** | How far the mid moves after a fill, in the direction that hurts the filled side. A negative markout means fills arrive when the price is about to go against you (adverse selection). |
| **Attrition** | Events dropped between the candidate list and the scored book. If drops depend on the outcome, the surviving sample is biased. |

## Licence

MIT. See [`LICENSE`](LICENSE).
