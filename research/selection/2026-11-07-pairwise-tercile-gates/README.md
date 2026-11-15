# Some pair of seller-favourable entry features selects events with more residual value than chance in all three blocks

| | |
|---|---|
| **Study** | `2026-11-07-pairwise-tercile-gates` |
| **Line** | `selection` |
| **Owner** | `jordanodorico` |
| **Status** | scored |
| **Pre-registration** | [`prereg.md`](prereg.md), record `outputs/research/prereg_2026-11-07-pairwise-tercile-gates.json` |

## Why it matters

Every single-feature selector in the record failed, and the model zoo found no skill in
multivariate models fitted to returns. A fixed, theory-signed intersection of two overpricing
symptoms, scored on residual value rather than P&L, is the simplest combined gate that cannot
have been fitted to outcomes. If any pair carries selection skill in all three blocks, it is the
first selector in the programme to do so; if none does, two-feature gates on these features are
closed as a family.

## Closest prior work and closed studies

Closed rows: the term gate (does not carry forward), the move gate, the spread gates, own-history
richness, and the 375-strategy model zoo on 15:59 features. Published: Goyal and Saretto (JFE 2009)
sort on the implied-historical gap; Bakshi and Kapadia (RFS 2003) on the variance risk premium;
Dubinsky et al. (RFS 2019) price the scheduled jump. This study differs by fixing the sign of each
feature from those sources before any outcome, intersecting pairs, and scoring residual value with
one-sided exit legs kept at half the ask.

## Changes

2026-11-07: the exit-mark cache gained the leg marks and exit forward as stored columns so the
marks could be reconciled to the hedged-hold study's `exit_mid` (exact on 7,337 two-sided exits).
No rule changed.
