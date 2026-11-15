# Freeze note: B1 closing-auction hedging (trials 2,892 to 2,895)

Written 2026-11-15 02:20 EST, after the 2013-18 discovery read (diagnosis.log entry [4]) and
before any 2019-24 or 2025-26 read. The scorer b1_auction.py and its helper l2lib.py are frozen
as hashed below; ExecutionLeversConfig in earnings_iv_crush/config.py supplies every input and is
not changed before the held-out read. Nothing was tuned: the auction grid and fees are declared.

Held-out block: 2019-24, read once with `b1_auction.py --block 2019-24`. block_is_clean against
research/ledger/blocks.csv returns True for panels base_corrected and hedged_event_hold, period
2019-24, outcome hedged_hold, feature family execution_moc_auction. The hedged_hold outcome on
2019-24 has nevertheless been viewed by L1's descriptive corrections and by earlier trials, so the
read is labelled exploratory as well as held-out. The lever applies to every event and selects
none, so a prior view of the outcome cannot bias which events it touches.

Declared reading on 2019-24: the primary (H_B1 - H_corr at N = 1, a = 0.5 bp) and the
like-for-like secondary, with a*, exactly as on discovery. The primary already failed on
discovery, so B1 cannot pass as declared; the held-out read sizes the like-for-like secondary.

Frozen files (sha256):
- b1_auction.py: 89e2992f44a7d799cff6404783433453d8bb4b9b15ff3ff1c3e339d1c24fadca
- l2lib.py: ed65c9025e91eb16c2e11e56bf5fe9e924f8f7fcf6e27bc14abeed68d7160a63

Self sha256 (sha256 of every byte above this line, LF endings): af54d1625a62b7d15763b7237e14c5a8a43d0037ed84b66ae78be0603bd42593
