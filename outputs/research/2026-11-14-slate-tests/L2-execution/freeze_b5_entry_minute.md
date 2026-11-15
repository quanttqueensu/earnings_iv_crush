# Freeze note: B5 entry minute by causal spread state (trial 2,905)

Written after the 2023 discovery read (diagnosis.log entry [15]) and before any 2024 read. The
scorer b5_entry_minute.py and the minute grid it reads are frozen as hashed below (the grid,
_cache/b5_minutes.parquet, was built for 2023 and 2024 together before any scoring, from quotes
only). The rule is unchanged from diagnosis.log entry [14].

Discovery failed the declared pass rule (interval includes zero, N = 213), so the single 2024
read is exploratory. The 2023-24 entry_execution family on these tick files was read by 1,779 and
1,780, so the block is not clean for the outcome family in spirit, though block_is_clean has no
row for panel broad_entry_ticks, period 2024, feature family entry_minute_spread_state.

Reading: paired mean with a date-clustered interval, the timing-null percentile, the
always-first-minute control and the drift and half-spread split, with
`b5_entry_minute.py --block 2024`.

Minute grid _cache/b5_minutes.parquet sha256: 1da8c7974bb626090ab38c889dbeff3e62ce31b1560b302e46b52fa625c01b90

Frozen files (sha256):
- b5_entry_minute.py: 82d6a27f056847ea5861b1a01f48877c852c95a697341e8e9025acae55aad273
- l2lib.py: ed65c9025e91eb16c2e11e56bf5fe9e924f8f7fcf6e27bc14abeed68d7160a63

Self sha256 (sha256 of every byte above this line, LF endings): cd5129660a628b36afc67e41b814e9b2149d29cc2e5b388266747181b5f561c3
