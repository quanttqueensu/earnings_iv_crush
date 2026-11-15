# Freeze: EIA Wednesday event variance, held-out read

Written 2026-11-13 after discovery trials 2172 to 2177 and before any held-out outcome was
computed. The SHA-256 of this note is in `freeze_eia_heldout.md.sha256` (a file cannot contain
its own hash); the scorer refuses to run on held-out unless that sidecar matches this note and
this note contains the scorer's hash.

## Frozen files

| File | SHA-256 |
|---|---|
| `eia_event_variance.py` (held-out scorer) | 2df020b63943b22b54488fd4a1de990125bee6cb01a2c3b3e012493b829b9d13 |
| `prep_eia.py` | c3ec666861e4d23cd93ca086d6688390f924f49601b0f98f4bd3f9aae161e120 |
| `raw/OVX_History.csv` | a6630eb64a2737533691a9750d4d19e5ec1872db221be77aa8725b7027720b42 |
| `data/wti_daily.csv` | 184fc816a76665ba29af49a9a13c3ecd7cd1d6250e1dbdb88a3ee483604250a7 |
| `diagnosis.log` as of entry 5 | 006d05be84fd66a23615e2c7bb99969a584432ddfa8ee95370f2f7d0100c8433 |

## What is read, once

Both statistics come out of one run of the scorer per realised series.

- **T2176, seller.** g = I - B, where B = mean|r_Wed| / mean|r_Tue| and I = sqrt(mean dV_Wed /
  mean dV_Tue). Discovery: g = -0.17 [-0.45, +0.15], N=302 weeks (failed).
- **T2177, buyer.** R_buy = mean|r_Wed| / (0.798 sqrt(mean dV_Wed)) - 1, the gross return at
  the mid on a one-day ATM straddle bought at Tuesday's settlement and held to Wednesday's.
  Discovery: +5.8% [-10.7%, +29.0%] of premium, N=302 weeks (failed).

Both failed discovery. The held-out read is an out-of-sample check of the direction, not a
rescue: a held-out pass on either is reported as exploratory, never as a finding.

## Blocks and series

- Primary: realised from NYMEX WTI contract-1 settlements, 2021-01-01 to 2024-04-05 (the EIA
  futures series ends there).
- Secondary: realised from Cushing spot, 2021-01-01 to 2026-11-11.
- Same filters as discovery: holiday weeks Monday to Wednesday dropped, roll weeks dropped by the
  calendar rule with a two-business-day buffer, consecutive-weekday pairs only.

## Pass rules (unchanged from diagnosis.log entries 1, 4 and 5)

- Seller: lower bound of g above 0, and g / I above the reference half-spread share.
- Buyer: lower bound of R_buy above 0, and R_buy above the reference half-spread share.
- Reference half-spread share, one way, as a share of straddle mid: 2.5%, the USO 5 and 7
  calendar-day ATM straddles in lane N17's delayed snapshot of 2026-11-13 14:35 ET
  (`../N17-commodity-etf-options/spread_table.csv`: 2.44% and 2.62%). No CL weekly option quote
  has been measured; the same snapshot's 0-day USO straddle pays 11.1% one way, so a one-day
  contract is likely costlier than this reference, which makes the bar lenient.
