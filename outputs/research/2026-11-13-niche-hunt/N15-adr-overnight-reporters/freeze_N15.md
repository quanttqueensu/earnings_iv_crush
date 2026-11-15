# Freeze, lane N15 (foreign issuers reporting outside US hours)

Frozen on 2026-11-13 before any 2026 event was built or scored. The 2026 block (D1 in 2026,
cached chains to 2026-05) is read once by `scripts/score_heldout.py`.

Confirmatory configuration: trial 2,503. Foreign issuers (OVS, FUS and CAN as fixed in
`diagnosis.log` entry [2]) against week- and tenor-matched US reporters; events kept only when the
entry chain shows a pending announcement (two-expiry jump variance > 0); short front ATM straddle
sold at the D1 15:59 bid, bought back at the D2 15:59 ask, USD 0.65 per contract per leg; B on
m0 = 0.20 forward + bid, per event, net at the touch.

Pass, both required: (a) the mean of B foreign minus matched control above zero with the
date-clustered 95% lower bound above zero; (b) the foreign mean B with its lower bound above zero.

Pre-declared robustness read, not a pass route: trial 2,504, the same with unquoted exit legs
valued at intrinsic plus USD 0.05.

Discovery (2025) results behind the freeze: trial 2,502 F mean B -3.76% [-5.96, -1.73], N=87;
trial 2,503 -2.82% [-5.06, -0.74], N=73, difference to control -0.16 points [-2.75, +2.16];
trial 2,504 -3.60% [-5.62, -1.65], N=92. All fail both rules.

SHA-256 of scripts/score_heldout.py: 43f873cb16b200f80016ebee22220440b10973dcf5071d20c2bf3c8910fe43f0
SHA-256 of scripts/score.py: 49e6195e96b29050f8d642cf1a6d2ab30affb2931a8128bdf400fa4c80174d6f
SHA-256 of scripts/build_events.py: 9d3ff4f0e0c52c1f5d48097ad61aac4edcc0c5f2fad2b2c86967271e9117adad
SHA-256 of scripts/bracket_check.py: 3413054a30d085477c0db900a5fb7807bacb5dcda39c01174699e48a7766d07e

SHA-256 of this note above this line: 616e8949f4f1cebe6c3757ed16f451432cbd0beecf0fba87cbc3f32574b1f99a
