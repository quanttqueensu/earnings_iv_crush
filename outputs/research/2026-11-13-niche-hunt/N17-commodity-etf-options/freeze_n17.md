# N17 freeze note: report-day variance in commodity and rates ETF options, held-out read

Written about 14:58 ET on 2026-11-13, after discovery runs 1 to 4 and before any held-out
statistic was computed. The held-out scorer was written before this note. The SHA-256 of this
note is recorded in `diagnosis.log` immediately after it is saved.

## What is frozen

The held-out read runs `event_scorer.py --block heldout` once, on 2021-01-01 to 2026-10-30.
The scorer refuses to run unless this note exists and carries its hash.

- event_scorer.py SHA-256: 5b72b1c0f9ce72be0febef4d371be670d5868f1c0fc52b6eda541fcacebe8dd1
- cost_basis_frozen.csv SHA-256: ddfd2408664f4d6366e43c76a3f0053ef8b3840c0de9edb519c48f3b5f30b056
- lump_fractions_discovery.json SHA-256: 23cbbc05038cea02cfa99ee906d523a9d77cfcb24e0fd3619cc0220204a9f8eb
- diagnosis.log at freeze SHA-256: a13e35470e6878d650f3feecd7ba402d535f2b475341458c47611845ca4cfe33
- raw/cboe_OVX.csv 13aafc0ce1ff750dcb110c703f7e4e8ac731bf856b837e0a6cc9cdaaebf911ab
- raw/cboe_GVZ.csv 1c275126fad88f8b0ea2426d02e6116c417b174a1779514d0f00b23ec70ca9ed
- raw/cboe_VXSLV.csv b2ed532e9a0eacd4577fd9c946af6975312f09608e8aaee204428b9ed785d6f9
- raw/cboe_VXTLT.csv 606c30c132efdc3b22282f32ed23deeee599ab18aa3239e69886b044b7398144
- raw/cboehist_USO.csv bfbd33530da56bdba219ff0a5f2d4a44d03d84e85cd267175f48801cddd88895
- raw/cboehist_GLD.csv 2fccad54b3386c50d2a204d76835d72b44bb9a0a740cfc16b96b50242640295d
- raw/cboehist_SLV.csv 61ade7bd82e440a7873acbc56fe3c071a2ac680cf399188dcaa113b0fddcb2c4
- raw/cboehist_TLT.csv 6c75e2f383f9ebde32d0064f71798ffbf312bf9d34e008dfed110fbf72e8d196
- data/cache/index_events/macro_releases_2016_2026.csv 78f52e297f34c3e52ebe9a70e53d33849fa875830eaf430802bdd43ca3b9082a

## Statistic and rule (unchanged from the pre-registration and its two amendments)

Per event, the one-day P&L of a short 30-day variance swap from the Cboe index close before the
report to the close of the report day, expressed as a share of an ATM straddle premium at two
tenors: 30 days (share30) and 7 days (share7, with the family's discovery lump fraction in the
denominator). Gross at the mid from index closes, model-based, not a tradeable level.

- S1: event minus the mean of matched non-report controls, date-clustered 95% interval.
- S2: event minus the round-trip touch plus IB commission measured on the 14:33 ET snapshot of
  2026-11-13 (median over ATM straddles at 21-35 days for the 30-day tenor, 5-10 days for the
  7-day tenor), date-clustered 95% interval.
- Frozen costs, share of straddle mid, round trip including USD 2.60 commission per straddle:
  USO 7.53% (30d) and 5.51% (7d); GLD 2.82% and 2.88%; SLV 3.47% and 6.52%; TLT 4.50% and 10.34%.

Pass (per pooled family and tenor): S1 lower bound above zero and S2 lower bound above zero.
Both: viable pending a priced data pull. S1 only: a premium exists at the mid but not net of the
touch in this vehicle. Neither: no event surplus in the vehicle.

## Status of each family on the held-out block

- F1 USO, EIA WPSR (trials 2562, 2575): a clean held-out test. No held-out OVX result from any
  lane has been seen.
- F2 GLD, F3 SLV, F4 TLT, CPI, NFP and FOMC (trials 2563-2574, 2576-2587): the 2021-2026 block
  has been read by lanes N05 (VXTLT) and N12 (GVZ, VXSLV) with near-identical constructions, and
  their held-out results were read here before this freeze. These rows are descriptive
  replications on a viewed block. They cannot pass, and they are reported for the net-of-touch
  translation only. TLT FOMC, named as a secondary in the pre-registration, falls under this
  label: N05's held-out FOMC surplus was already known to be +0.0019 [-0.0248, +0.0255] (97.5%).

## Kill criterion for the lane

F1 fails S2 on held-out at both tenors. Then no commodity or rates ETF option class shows a
report-day premium that clears its own touch on free data, and a metered pull is justified only
for a question this pilot cannot answer (the event-day expiry vehicle, see `evidence.md`).
