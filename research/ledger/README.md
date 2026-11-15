# Ledgers

Two append-only records that make the research protocol checkable (`docs/PROTOCOL.md` P19, P20).

`blocks.csv` has one row each time outcomes on a data block are viewed, by a trial or a
descriptive query: panel, period, outcome family, feature family, who viewed it, and whether it
was a trial or descriptive. Write rows with `protocol.log_block_view`; check a block with
`protocol.block_is_clean`. A `*` matches every family. The first row marks the 2025-26 hedged
event hold as viewed for every family, because trials 1,593 to 1,615, G1 and the entry-clock
work all read it before this ledger existed.

`trials.csv` has one row per hash record. Rows marked `pre-ledger` were frozen before the ledger
and carry their verdicts in `docs/RESEARCH_STATE.md`. From the first trial frozen under P16 to
P21, each row records its LOND index (counted from 1 under the new regime), its discovery
p-value from `protocol.date_clustered_pvalue`, the alpha from `protocol.lond_alpha` (advisory, see P20),
and the verdict.

Families in use: outcome `tail_and_buyback`, `move_size_and_buyback`, `hedged_hold`,
`buyback`, `residual_value`, `hold_vs_buyback`, `entry_execution`, `exit_execution`,
`index_event_straddle`, `event_straddle`, `entry_day`; feature `peer_shock`, `distress`,
`price_path`, `earnings_variability`, `own_history`, `term_structure_jump`, `characteristics`,
`sizing`, `macro_state`, `forensics_liquidity_size`, `quote_surface_flow`,
`event_richness_own_history`, `entry_clock_and_hold`, `entry_clock`, `calendar_niche`,
`post_announcement_rules`, `contract_choice`, `post_event_vol_forecast`,
`structural_jump_model`, `walk_forward_model`, `resting_exit`, `megacap_reporters`,
`adcomm_product`, `early_entry`, `name_persistence`. Add new names here when a study needs one.

Rows with regime `exploratory-unhashed` in `trials.csv` are the two 2026-11-13 alpha hunts: one
row per lane, pointing at that lane's own trial log, with the number of distinct trials it
scored. They count towards the total and carry no LOND index, because their freezes were notes
without hashes.

Both files are append-only, so a malformed or wrong row is never edited. A row with regime
`correction` restates the row above it that it corrects, says what was wrong, and declares 0
trials, so it never changes the count.

Rows with regime `exploratory-unhashed` after the two 2026-11-13 alpha hunts follow the same
pattern for the later 2026-11 programmes (the niche hunt, the earnings-adjacent hunt, the slate
tests and the deep-learning programme): one row per lane, plus team-lead rows for trials charged
at review.
