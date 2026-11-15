# Freeze note: B6 per-event expiry choice (trial 2,901)

Written after the 2013-18 discovery read (diagnosis.log entry [8]) and before any 2019-24 read.
The scorer b6_score.py, its helper l2lib.py and the builder b6_build.py are frozen as hashed
below, as is the later-contract cache's builder output (_cache/b6_later.parquet, built for every
CRSP event before any scoring). The rule is unchanged from diagnosis.log entry [6].

Discovery failed the declared pass rule (interval includes zero) although the null percentile
was 97.8. The single 2019-24 read is therefore exploratory: it cannot turn B6 into a finding.

block_is_clean (research/ledger/blocks.csv), period 2019-24, outcome hedged_hold, feature family
execution_expiry_choice: True for base_corrected and hedged_event_hold. The hedged_hold outcome on
2019-24 and the later-expiry outcome (closed study, 2026-11-02) have both been viewed before.

Reading: the paired mean, its date-clustered interval, the matched null percentile and the
component decomposition, exactly as on discovery, with `b6_score.py --block 2019-24`.

Later-contract cache _cache/b6_later.parquet sha256: 4b3ee94b52e0414d28a8babdbe808033ec9fce642919fbb48536885adef83690

Frozen files (sha256):
- b6_score.py: 916223847a1fd53d1c41ddda83a51ce6a2027edd8228c8a019d82005327d78f3
- b6_build.py: 333e114181169da0383785dcc12ce9914ee7f259395f1a4176479db90f447ee3
- l2lib.py: ed65c9025e91eb16c2e11e56bf5fe9e924f8f7fcf6e27bc14abeed68d7160a63

Self sha256 (sha256 of every byte above this line, LF endings): 87112f6f8d0a49c3c92266e9e363e3809005362ccea2f487edf6bdaddb2c0dd1
