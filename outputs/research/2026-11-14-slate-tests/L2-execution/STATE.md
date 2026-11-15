# L2 execution and cost: state

Updated 2026-11-15 03:08 EST. Hard stop 07:30 EST. Lane complete; final message sent.

## Done

- Infrastructure: `_cache/paths.pkl` (`build_paths.py`, `build_paths.log`); `l2lib.py` and
  `l2fees.py` (both hashed by freeze notes: never edit); `freeze.py`. Config:
  `ExecutionLeversConfig` / `EXECUTION_LEVERS` in `earnings_iv_crush/config.py`.
- B1 `b1_*.json`, `freeze_b1_auction.md` (declared comparison invalid: fee asymmetry).
- B10 `b10_*.json` (re-run with the 1% cap, 02:54 to 02:57); `hedge_commission.parquet`,
  `hedge_commission.README.txt`, `hedge_commission.log` (lead told 02:58).
- B6 `b6_*.json`, `freeze_b6_expiry_choice.md`. B2 `b2_*.json`, `freeze_b2_mvdelta.md`.
- B4 `b4_1779.json`, `b4_1819.json` (re-run 03:00, identical to the originals).
- B5 `b5_*.json`, `freeze_b5_entry_minute.md`. B8 `b8_*.json`, `freeze_b8_strangle.md`.
- B11 `b11_2013-18.json`, `freeze_b11_band.md`, `b11_2019-24.json` (read once),
  `b11_2025-26.json` (exploratory).
- Review fixes: diagnosis [22] to [27]; `sources.csv`, `sources/`; evidence.md and trials.csv
  updated. Old outputs before the fixes in `_cache/old_*`, `_cache/*_before_review.*`.
- Tests: `tests/research/test_execution_levers.py`, 51 pass; full suite 1,839 pass; mypy clean.

## In progress

- Nothing.

## Not started

- Nothing in scope. 2019-24 is spent for every L2 family; any further variant is 2025-26 only.

## Trial numbers

Used: 2,892 to 2,916. Unused: 2,917 to 2,951.
