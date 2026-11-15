# Freeze: N12 metals-macro held-out read

Written on 2026-11-13 after the discovery read (diagnosis.log entries 1 and 2) and before any
held-out outcome was computed. The held-out block (2022-01-03 to 2026-10-30) is read once, by the
scorer below, with the construction, statistic and pass rule of diagnosis.log entry 1 unchanged.

Trials read on held-out: 2,412 (primary, GLD pooled), 2,413 (secondary, SLV pooled), 2,414 to
2,416 (descriptive, GLD by release type). Trial 2,417 stays discovery-only. Pass for 2,412 and
2,413: held-out mean S > 0 with the date-clustered 95% lower bound > 0. Economic gate after the
read: s03_gate.py, pi_1 > c_1 or pi_3 > c_3 from the 2026-11-13 GLD and SLV snapshots taken while
the options session was open.

Hashes (SHA-256):

- held-out scorer scripts/s02_score.py: da11b484313670dd4f1e6bb9ebfeaace6c67fb51aa6105a5309d8b567f1f9a59
- gate script scripts/s03_gate.py: 72bfe981b4a243928d91303c5fc423b9c530e2f112e1f07bb1ca6e53ba4e8e52
- panel builder scripts/s01_build.py: 19b01f707e2be9fab7a968d61c638e4904887238b4a3105e5ff991a575ea99fd
- events.parquet: daa6724d00efb2fe0ec1d39b87b45afad70bccba820afe1faad4d4208dbfb7cc
- panel.parquet: 7d2e611411e454fe0c8c77b57d2aab9243223836cd801c5d29a9746b9aa7271e
- diagnosis.log at freeze: 098a9ca75430c2fc91fe82cff0b4d5a556203f4f959cea9c08e226b1addf502c
- calendar data/cache/index_events/macro_releases_2016_2026.csv: 78f52e297f34c3e52ebe9a70e53d33849fa875830eaf430802bdd43ca3b9082a

SHA-256 of this note above this line: b59abfe64800817e378227a0cba70feb77c27f45ae07326a7d924e65ee1ddea4
