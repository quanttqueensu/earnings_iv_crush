# Freeze: FOMC short-rate variance premium from SOFR option-implied distributions

Frozen before the held-out block (2025-01-01 to 2026-11-12) was read. The design is the one
pre-registered in diagnosis.log entry 1, unchanged; entry 2 records the discovery reading and why
no iteration on this file can fix it.

## What is frozen

Trial 2,238 (primary): variance from the published quartiles, horizons 30 to 730 days, two-row
window t-1 to t+1, per-date mean of the Bachelier short-straddle return on premium, gross at
settlement-derived marks. P1: FOMC minus control effect above zero with the 95% interval above
zero. P2: FOMC return net of the half-tick four-leg hurdle above zero with the interval above zero.

Trial 2,239 (secondary, not passed on): variance from bins, the bp^2 decomposition of the
premium into implied roll-off excess and realised excess.

Sensitivities (not trials): FOMC events without coincident CPI or payrolls; SEP and non-SEP.

## Discovery reading (2023-05 to 2024-12, already seen)

Effect -0.46% of premium [-5.02, +3.32], 14 FOMC dates against 47 controls. Expected power on
held-out is low: the minimum detectable premium is about 390 bp^2, larger than the whole implied
event variance, so a pass would be surprising and a fail is uninformative about the weekly vehicle.

## Code and data at freeze (sha256)

771e5d1cd42e743f336e4498c1c30fd70942fbd4b86852bb52987813d7e61607  score_heldout.py
7535f3e43f275e06520f9becd0056866b55aee22cadbcae8c9c1bdd4ee0dafa6  n06_lib.py
7ac75c661e295e7870f62a14d81e9c91f3f2ae822139a55065eab963eb936068  data/mpt_histdata.xlsx
32fc59d2020f49d71343e27004bcc55fb22abbb52d0a821a1b5bf3d2fdad509a  diagnosis.log (entries 1 and 2)

The SHA-256 of this note, computed over every line above the final line, is in
freeze_2026-11-13_fomc-variance-premium.sha256 and repeated below.

Freeze time: 2026-11-13T19:44:00Z
Note body sha256: 99a1c6af5785a72350eaf62804acce31ab6c8092f17b635fd4eaba2d390633d7
