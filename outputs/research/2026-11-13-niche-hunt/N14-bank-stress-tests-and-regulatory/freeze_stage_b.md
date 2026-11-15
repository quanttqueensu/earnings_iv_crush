# Freeze: N14 stage B, held-out read (2026-11-13)

Written before any held-out (cycles 2023, 2024, 2025, 2026) outcome was computed or printed.
The held-out scorer is `stage_b_options.py --block heldout` exactly as on disk, with
`N14_EARNINGS_RULE` unset (round 2: no earnings rule on either leg), reading chains cached under
`chains/` by `stage_b_options.py --fetch`.

- stage_b_options.py SHA-256: 6592a8b2fa239de9d939298e64f7bb838c0d742bebb106500f50e69deeb7dc17
- dolt.py SHA-256: 8a04d1838cb307644555ae81a6b219a5e3f1287d10a3f104dd18c419a25d97d4
- stress_calendar.csv SHA-256: 7c3e77099e010f89b9b0c4e0d4d211b57513401601d6001f0792e221908ae49a
- This note's SHA-256 is in freeze_stage_b.sha256 (computed on this file as written).

## Trials read

- 2479: short front straddle over the stress-test window (entry: last end-of-day snapshot on or
  before the results day; exit: first snapshot on or after the session after the capital-action
  night), net at the touch, share of m0, event minus mean of same-name controls at -28 and -35
  days. Pass: event level > 0 and event minus control > 0 with the date-clustered lower bound
  > 0 (diagnosis.log entry 1).
- 2480: IV change on the traded contract, event minus control, vol points. Descriptive: a crush
  would show as a negative value.

Provenance: round 2 failed discovery on its level (-0.009 of m0 [-0.041, +0.029], N=39, 4
cycles). This read is a confirmation of that fail, not a promotion. Expected held-out N: about 40
event windows over 4 cycles; the interval will be wide whatever the sign.
