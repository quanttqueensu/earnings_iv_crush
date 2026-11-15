# Freeze: N03 storage-day variance and storage-day futures short, held-out read 2019-01 to 2024-04

Frozen 2026-11-13, before any held-out (2019-01-01 to 2024-04-05) outcome was computed or printed.
The only held-out quantity seen so far is the funnel count of kept weeks over the whole file,
which is calendar-determined.

## Inputs and code

- Data: `data/futures_daily.csv`, SHA-256
  `c8f28812124a467feb4cfd751cc5d1d1dcfac0cd49ffd43a0c8f101b38fd7ff8`, built by
  `scripts/prep_data.py` from the EIA files in `raw/` (NYMEX Henry Hub settlements, contracts 1
  to 4, ending 2024-04-05).
- Held-out scorer: `scripts/score_heldout.py`, SHA-256
  `70224fbb89b935ee8966022d9d7697aef10ce3b4afb4b9824e194e14d61097c8`.
- Library it imports: `scripts/lib.py`, SHA-256
  `4e6a5d0b55dcb08df5df204b5a3d7612da79c8379059ae856e645a28d6ef6cff`.
- This note's own SHA-256 is in `freeze_heldout.md.sha256`, written immediately after this file;
  the scorer refuses to run if either hash disagrees, and refuses a second read.

## Rules, unchanged from the pre-registration (diagnosis.log entry 1)

- **2142**: rho on C1, storage-week Thursday settle-to-settle squared return over the matched
  Tue/Wed mean, minus one, week-clustered bootstrap (10,000, seed 0). Pass: lower bound > 0.25.
- **2143**: the same on C2. Pass: lower bound > 0.25. Robustness only.
- **2144**: short C1 from Wednesday to Thursday settlement, net of 1 tick and $2.50 per side.
  Pass: net mean lower bound > 0 and event-minus-control lower bound > 0. Failed discovery; the
  held-out read is an out-of-sample check of Prokopczuk, Wese Simen and Wichmann (2021), not a
  rescue.
- **2145**: the same on C2. Failed discovery; same status as 2144.

## Expected results, stated now

2142 and 2143: rho positive, point estimate between 0.3 and 0.8; the lower bound may fall under
0.25 given the 2011-18 discovery read of +0.42 [+0.07, +0.89]. 2144 and 2145: net mean near zero,
fail. Whatever 2142 shows, it is a calibration of the event's size, not a premium: no option
price enters any statistic here.

Path: C:\Users\jodor\Documents\QUANTT_IVCrush_Project\outputs\research\2026-11-13-niche-hunt\N03-natgas-storage\freeze_heldout.md
