# N09 held-out freeze

Written 2026-11-13, after discovery closed (diagnosis.log entries 1 to 3) and before any held-out
outcome was computed. The held-out block is 2017-01-01 to 2026-11-12 for FOMC; it is read once.

Primary: T2330, short the front monthly VX from the settle before a scheduled FOMC statement day
to the settle on that day, sized by one over the trailing 20-session standard deviation of daily
front-month settle returns measured to the prior session. Cost 0.055 VIX points round trip per
contract. Pass: the date-clustered 95% lower bound of the net return per sigma is above zero and
the lower bound of the surplus per sigma over same-weekday controls (within 35 days, excluding
FOMC, CPI and NFP days) is above zero. Failure of either closes the configuration.

Secondaries, exploratory, not findings: T2322 (the same trade unscaled) and T2328 (VVIX change on
FOMC days minus controls).

Files fixed by this note:
- scripts/score_heldout.py SHA-256: f13fa6c73d10738356936cab3250156710a3c607e0b36514cb2bbb67e3ee4b38
- scripts/vxlib.py SHA-256: d99835c658721dfba093fc8145417c4129fb3e5e0c5f9f05002826c41c36c91f
- scripts/score_round2.py SHA-256: 6b83327af6b9174875f3899c3701453956500803c2ef9623cbc0277abbc1caaa

This note's own SHA-256 is recorded in freeze_heldout.sha256 beside it, computed over this file
as written.
