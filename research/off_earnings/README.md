# Away from earnings

The same signals with the announcement removed, and scheduled-event trades that are not single-name earnings: the de-eventised term slope (Vasquez 2017), PEAD on SUE, SPY across macro releases, and the pivot screening programme.

Closed studies here are frozen: their logic is not edited, so each recorded result reproduces. Import their helpers if useful, but start new work from `research/_template/` (see `research/README.md`). Run a study from the repository root, for example `python research/off_earnings/pivot_vasquez_slope.py --help`.

Moved here from `scripts/` on 2026-10-18; a pre-registration or findings note that cites `scripts/<name>.py` or `_private/<name>.md` means the file of the same name in this folder.

## Code

| Module | What it does |
|---|---|
| `pivot_vasquez_slope.py` | Candidate #6: the term-structure slope sort, with the earnings event removed |
| `research_p2_term_slope.py` | P2: the de-eventised, short-dated term-structure slope sort on free DoltHub chains |
| `research_pead_sue.py` | Post-earnings-announcement drift on analyst SUE, dispersion and revisions |
| `research_spy_macro.py` | Pre-registered test: SPY straddles across scheduled CPI, payrolls and FOMC releases |
| `validate_pead_car_harness.py` | Does the conditioner study's CAR harness reproduce PEAD where PEAD is known to live? |

## Pre-registrations

Frozen texts, verified byte for byte against `outputs/research/prereg_*.json` by `tests/test_preregistrations.py`. Never edit one; amend with a new dated file.

- [`p2_term_slope_prereg.md`](preregs/p2_term_slope_prereg.md)
- [`p2_term_slope_prereg_amendment_01.md`](preregs/p2_term_slope_prereg_amendment_01.md)
- [`p2_term_slope_prereg_amendment_02.md`](preregs/p2_term_slope_prereg_amendment_02.md)
- [`spy_macro_and_runup_amendment_01.md`](preregs/spy_macro_and_runup_amendment_01.md)
- [`spy_macro_and_runup_amendment_02.md`](preregs/spy_macro_and_runup_amendment_02.md)
- [`spy_macro_straddle_prereg.md`](preregs/spy_macro_straddle_prereg.md)

## Findings

- [`p2_term_slope.md`](findings/p2_term_slope.md): P2: the de-eventised, short-dated term-structure slope
- [`pead_iv_conditioner.md`](findings/pead_iv_conditioner.md): Can option-implied earnings measures sharpen PEAD?
- [`pivot_dossier.md`](findings/pivot_dossier.md): Pivot research dossier
- [`pivot_verdicts.md`](findings/pivot_verdicts.md): Pivot test verdicts
- [`spy_macro.md`](findings/spy_macro.md): SPY straddles across macro releases: not testable on the free DoltHub source

Verdicts and key figures for every study are tabulated in [`docs/RESEARCH_STATE.md`](../../docs/RESEARCH_STATE.md).
