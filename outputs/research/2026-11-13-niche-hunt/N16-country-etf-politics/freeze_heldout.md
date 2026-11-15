# Freeze note: N16 held-out read

Written 2026-11-13 after every discovery result in diagnosis.log and before any held-out
outcome was computed. The held-out block (event entry dates 2020-01-01 to 2026-11-12) is read
once by the two scorers below with no change to their logic. The statistics and pass rules are
those in diagnosis.log (pre-registration and amendment 1). Discovery failed for all four
trials, so no held-out result can become a finding; a held-out pass is recorded as
inconsistency across blocks.

Trials read: 2532 (Copom, no FOMC in window), 2533 (Copom with FOMC), 2534 (Brazil election
rounds 2022 and 2026, descriptive, N=4), 2535 (European elections and referendums, N=16
windows listed in amendment 1).

Scorer hashes (SHA-256):
    41e94d039a517d5b74d80bf2a00df409cbdbf37ddaa6d31e84c15787f61fb499 *score_events.py
    0daca7d7c1e0e78efe1907e84bd684c6b730bb10a5f28cba844adcf0d3164ace *score_elections_eu.py

SHA-256 of this note above this line: 8ba21618515de40b6b2683bc469b17ca1bc461f4b3d059950b425ead6c4a8301
