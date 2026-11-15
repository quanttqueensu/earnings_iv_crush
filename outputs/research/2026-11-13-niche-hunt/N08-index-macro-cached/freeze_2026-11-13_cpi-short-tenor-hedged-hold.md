# Freeze: short-tenor SPY straddle sold before 08:30 CPI and payroll releases, hedged to expiry

Frozen 2026-11-13, after discovery and before the single held-out read (trial 2,312). Nothing
below changes after that read. The held-out scorer was written before this note.

## Provenance and contamination

Discovery-derived (block D, entry sessions 2016-01-04 to 2024-12-31). The tenor cap came from the
round-2 diagnostic split by days to expiry (`s02c_diag.log`, trial 2,306), justified ex ante by
the event-share argument (a fixed release variance is diluted by each ordinary session in the
contract) but chosen after seeing the split. Under the cap every qualifying discovery event is a
CPI release (Friday payrolls always give an expiry four days out), so the rule is in effect "CPI on
a session with a next-session expiry". Twenty trial numbers were used before this freeze
(2,292 to 2,311, including the descriptive mechanism read 2,295 and diagnostic split 2,306); none passed the pre-registered discovery rule.

Held-out block H (entry sessions 2025-01-02 to 2026-10-30) is not clean for macro outcomes: the
frozen index study's amendment 03 printed close-to-close SPY short straddles across CPI and payrolls
on 2016-18 and 2025-26 pooled (-6.2% of premium, N=110) and FOMC longs on the same pool. This lane
has computed no T4 or short-tenor outcome on H. Whatever the read shows, the result is
exploratory.

## Rule (frozen)

- Events: D in the frozen calendar `data/cache/index_events/macro_releases_2016_2026.csv`
  (SHA-256 78f52e29...082a) with kind CPI or payrolls, D an NYSE session.
- Contract: the frozen index study's B3 contract for the session before D (shortest SPY expiry
  strictly after D with a two-sided pair at 15:59, strike minimising |C mid - P mid|), kept only if
  its expiry is at most 3 calendar days after entry.
- Trade: sell at the 15:59 bids; delta-hedge at each close from the entry close to the last session
  before expiry at the entry straddle implied volatility (ACT/365); settle at intrinsic on the
  expiry close with `HEDGED_NET` (assigned share netted against the hedge, 1 bp equity floor, USD
  0.65 per contract on the two entry legs). Unit: entry mid premium, per trade, net.
- Controls: same trade on nights with no CPI, payrolls, FOMC or PCE on the entry or event session,
  same weekday, same calendar days to expiry, within 60 sessions; at least 5.
- Statistic: event-book mean and paired mean (event minus matched-control mean),
  `protocol.date_clustered_ci` (mean, 5,000 draws, seed 0, 95%).

## Discovery numbers (block D)

Trial 2,307, SPY, N=90: book +9.38% of premium [-2.31, +20.46], paired +10.88% [-0.69, +21.96],
t 1.93, per-trade Sharpe +0.173, skew -1.09, positive in 6 of 9 years. Fails the pre-registered
discovery rule. Secondary: QQQ with PCE added paired +11.36% [+0.94, +21.33], N=102 (trial 2,310).

## Held-out criterion (trial 2,312)

PASS if the H event-book mean > 0 and the H paired mean > 0 with its 95% interval excluding zero.
Expected power is low: with a per-trade standard deviation near 0.54 of premium and about 20 events
in H, the interval half-width is near 24 points of premium against a discovery effect of 11. A FAIL
with a positive point estimate is a sign check, not a refutation; a negative point estimate counts
against the idea. QQQ, IWM and the PCE-augmented SPY book are reported and cannot rescue SPY.

## Hashes

- Held-out scorer `s03_heldout.py`: 77c10537b2f3ac93794f148a282def6df651f09091d342101278d67ac55193e1
- Its imported matcher `s02_discovery.py`: 7a010df79a52af7add7cb743a4339fd6cd7092ea411dedf1165e1b5d3ddc2aa2
- `trades_all.parquet`: 038dbf1ed6fdbef1dd26c0e229bf8a10f6bf28f6ae78d49acaf38e4ced423437
- `trades_round2.parquet`: e50f7b27524f274b9093439fe7c2c326f19a7c44ef07bef5f88a8b5b513c7271
- `calendar_flags.parquet`: 027fa434f9224dc0e02fdb6f4ce75a207f14d7781c356087c7a49cf515212ccf
- This note: SHA-256 of every byte above the next line, recorded in the line itself and in
  `freeze_2026-11-13_cpi-short-tenor-hedged-hold.sha256` (whole file).
SHA-256 of the bytes above this line: b9eeba67ce226789fc603f8e95762bd1eaf5dac4854d9008f23abf989ef816c3
