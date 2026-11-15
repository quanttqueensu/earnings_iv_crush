# Other markets

Scheduled-event volatility outside US equity options, run after the 2026-10-06 decision rule: Deribit BTC options across CPI, payrolls and FOMC, and Kalshi tail selling and maker bids. All lose at the touch or fail to replicate.

Closed studies here are frozen: their logic is not edited, so each recorded result reproduces. Import their helpers if useful, but start new work from `research/_template/` (see `research/README.md`). Run a study from the repository root, for example `python research/other_markets/research_deribit_macro.py --help`.

Moved here from `scripts/` on 2026-10-18; a pre-registration or findings note that cites `scripts/<name>.py` or `_private/<name>.md` means the file of the same name in this folder.

## Code

| Module | What it does |
|---|---|
| `research_deribit_macro.py` | Pre-registered pilot: the macro-release crush in BTC options on Deribit |
| `research_kalshi_maker.py` | Pre-registered test: the same Kalshi favourites, bought with resting bids instead of at the ask |
| `research_kalshi_replication.py` | Pre-registered replication of the Kalshi maker result on 81 release series it has never seen |
| `research_kalshi_tails.py` | Pre-registered pilot: selling both tails of Kalshi scheduled-release distributions |

## Pre-registrations

Frozen texts, verified byte for byte against `outputs/research/prereg_*.json` by `tests/test_preregistrations.py`. Never edit one; amend with a new dated file.

- [`deribit_macro_event_prereg.md`](preregs/deribit_macro_event_prereg.md)
- [`deribit_macro_event_prereg_amendment_01.md`](preregs/deribit_macro_event_prereg_amendment_01.md)
- [`kalshi_macro_tails_prereg.md`](preregs/kalshi_macro_tails_prereg.md)
- [`kalshi_maker_prereg.md`](preregs/kalshi_maker_prereg.md)
- [`kalshi_maker_replication_prereg.md`](preregs/kalshi_maker_replication_prereg.md)

## Findings

- [`deribit_macro.md`](findings/deribit_macro.md): The macro-release crush in BTC options: no event premium beyond the ordinary one
- [`kalshi_maker.md`](findings/kalshi_maker.md): Kalshi favourites bought as a maker: the sign turns, the interval does not clear
- [`kalshi_replication.md`](findings/kalshi_replication.md): Kalshi maker result does not replicate on unseen series
- [`kalshi_tails.md`](findings/kalshi_tails.md): Selling the tails of Kalshi scheduled-release distributions: not tradable at the touch
- [`2026-11-13-niche-hunt.md`](findings/2026-11-13-niche-hunt.md): Niche hunt: scheduled-event volatility beyond US single-name earnings (exploratory)

Verdicts and key figures for every study are tabulated in [`docs/RESEARCH_STATE.md`](../../docs/RESEARCH_STATE.md).
