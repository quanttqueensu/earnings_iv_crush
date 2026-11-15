# Freeze note: C8 trial 2,953, written 2026-11-15 before the 2019-24 read

Rule (unchanged from diagnosis.log section 3): on the megacap hedged-hold panel re-settled through
L1's build_one (c8_megacap_corrected.parquet), select the top causal tercile (min_prior 100) of
os_d1 = ln(100 x D-1 option contracts / D-1 CRSP shares). Primary: residual value selected minus
unselected, % of m0 per trade, date-clustered 95%, with the matched-null percentile; H_corr side by
side. Pass: residual value lower bound > 0, null percentile >= 95, H_corr difference > 0.
Declared secondary that decides the mechanism reading: the same contrast inside residual-tenor
strata (0-2, 3-4, 5-7, 8+ calendar days), weighted by selected count.

Search behind the frozen rule: one configuration scored (trial 2,953); its discovery figures are
+1.234 [+0.570, +1.897], null percentile 99.9, N=336, and tenor-stratified +0.242 [-0.303, +0.755].
Discovery t is about 3.6 on the primary (interval half-width 0.66).

Block status: block_is_clean returns True for option_stock_volume_d1 on 2019-24 under the panel
names hedged_event_hold, megacap and base_corrected, for both outcome families. The hedged_hold
family of the megacap 2019-24 block was read by the closed amendment 02, so the H_corr read is
exploratory; no residual_value view of the block is recorded.

Held-out block 2019-24 is read once with:
    python outputs/research/2026-11-14-slate-tests/L3-selection/c8_score.py --block 2019-24

Scorer c8_score.py sha256 894aad82209fdf526599dd8c735b22055a4bce44ab124502638540fbed8f0b39
Shared lib.py sha256 2c4b8201934453d2a4a6379d6424246bbdf90f571746747a0873554fdd12c7fa
Panel c8_megacap_corrected.parquet sha256 dc7ec4a367bc7f7de6ed89717f51cf369077ea5c3be05d705e2ad796d231c489
Note sha256 (of every byte above this line): f944e1a219ef335c0f6496bff7761f5b63b817007b833d02da2053fbde85fa36
