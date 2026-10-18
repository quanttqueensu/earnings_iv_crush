# Timing and holding

When to enter and when to exit: hold to expiry, the conditional hold and its frozen validation, the post-announcement straddle, post-announcement overpricing and the pre-announcement vega run-up. All closed.

Closed studies here are frozen: their logic is not edited, so each recorded result reproduces. Import their helpers if useful, but start new work from `research/_template/` (see `research/README.md`). Run a study from the repository root, for example `python research/timing/research_conditional_hold.py --help`.

Moved here from `scripts/` on 2026-10-18; a pre-registration or findings note that cites `scripts/<name>.py` or `_private/<name>.md` means the file of the same name in this folder.

## Code

| Module | What it does |
|---|---|
| `research_conditional_hold.py` | Pre-registered validation of the conditional hold-to-expiry exit on 2013-2018 |
| `research_hold_conditional.py` | Does a conditional exit rescue the mean advantage of holding to expiry? |
| `research_hold_holdout.py` | Does the conditional-exit cut survive out of sample, or is it in-sample selection? |
| `research_hold_inference.py` | Is the hold-to-expiry advantage over the next-session exit real, or noise? |
| `research_hold_to_expiry.py` | Does holding to weekly expiry beat the 8.55% exit cross? |
| `research_lossstudy_common.py` | Shared reconstruction of the honest q=0.80 term-only mega-cap book for the |
| `research_post_event_vrp.py` | Pre-registered test: post-announcement short straddle sold at the exit-day 15:59, held to expiry |
| `research_vega_runup.py` | Pre-registered test of the pre-announcement vega run-up (state of record section 2.5) |

## Pre-registrations

Frozen texts, verified byte for byte against `outputs/research/prereg_*.json` by `tests/test_preregistrations.py`. Never edit one; amend with a new dated file.

- [`post_event_vrp_prereg.md`](preregs/post_event_vrp_prereg.md)
- [`postea_prereg.md`](preregs/postea_prereg.md)
- [`postea_prereg_amendment_01.md`](preregs/postea_prereg_amendment_01.md)
- [`postea_prereg_amendment_02.md`](preregs/postea_prereg_amendment_02.md)
- [`vega_runup_prereg.md`](preregs/vega_runup_prereg.md)

## Findings

- [`post_announcement_overpricing.md`](findings/post_announcement_overpricing.md): Post-earnings volatility overpricing: pre-registered test, both controls fail, and the test is underpowered
- [`post_event_vrp.md`](findings/post_event_vrp.md): Post-announcement short straddle held to expiry
- [`vega_runup.md`](findings/vega_runup.md): Pre-announcement vega run-up (state of record section 2.5)

Verdicts and key figures for every study are tabulated in [`docs/RESEARCH_STATE.md`](../../docs/RESEARCH_STATE.md).
