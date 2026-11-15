# Earnings-adjacent hunt, 2026-11-14: summary

Artefacts (lane folders, scripts, logs and per-event files) are in `outputs/research/2026-11-14-earnings-adjacent-hunt/`, which is shared through the R2 bucket, not git: `python -m earnings_iv_crush.data.sync pull --only outputs/research`. Paths below are relative to that folder unless they start at the repository root.

Five lanes looked for return sources next to the earnings event rather than in the event straddle
itself: long gamma after the crush (E1), pre-event option flow as a stock signal (E2), spillover to
non-reporting peers (E3), expiry mechanics on the post-earnings expiry (E4), and a literature map
with quick screens (E5). Rules are in `BRIEF.md` and `LANES.md`; trial numbers were reserved in
`RESERVED_TRIAL_IDS.md` before any lane started.

Everything here is exploratory. Freeze notes hash themselves and their scorers but were not filed as
pre-registrations, and several held-out blocks share events with earlier studies (review item 4).
All data are real: CRSP daily, Databento OPRA quotes cached by earlier studies, Alpaca daily option
bars, and the project's hedged-hold panels. No paid pull was made.

## Verdict

No lane produced a tradeable candidate. Ten frozen rules or screens were read once on a held-out
block; none passed, and every one had already failed on discovery. An independent
review (files, not conclusions) found nothing that could flip a verdict. The hunt's useful output is
two valuation defects in the project's own books (section "Defects found").

## Results by lane

Basis is per trade and net at the touch unless stated: option legs at the quoted bid or ask plus
USD 0.65 per contract per leg, stock legs at a half-spread plus 1 bp. Intervals are date-clustered
95%.

| Lane | Frozen rule | Discovery | Held-out (read once) | Mechanism reading |
|---|---|---|---|---|
| E1 gamma scalp | 2,682: buy the held straddle at the 15:01 ask on the reaction session, hedge every 5 minutes, sell at the 15:59 bid | -11.66% of debit [-13.01, -10.24], N=578 (megacap 2023-24, broad 2025 H1) | -19.82% of debit [-21.37, -18.24], N=682 (broad 2025-07 to 2026-06) | gross at the mid +0.86% [+0.46, +1.26] against a 10.57% round-trip option touch; the reaction hour gives no more than the D-1 hour (+0.23% [-0.27, +0.72]) |
| E1 mirror | 2,691: hedge the short hold from 15:01 on the reaction session instead of at the close | -0.31% of m0 [-0.48, -0.14], N=578 | not read | intraday hedging of the short costs money; supports close-only hedging |
| E2 informed flow | 2,721: trade the stock against the last hour's signed ATM option flow, 15:59 to 15:59 | +0.335% of stock notional [-0.180, +0.828], N=593 (2023-24) | +0.094% [-0.452, +0.631], N=419 (2025-26), null percentile 72 | the declared primary (2,712, with the flow) failed with the wrong sign; the reversal was adopted after discovery |
| E3 spillover | 2,742: trade non-reporting same-SIC3 peers in the direction of the reporters' reaction, next session | -4.51 bp [-10.20, +1.07], N=4,803 (2013-18) | -9.94 bp [-15.48, -4.54], N=9,779 (2019-24) | transfer real but complete by the reaction close: same-session co-move +38.1 bp [+32.1, +44.3] |
| E3 option arm | 2,749: peer variance on the reporter's night over ordinary nights; buying needs about 3.4 | 0.97 [0.88, 1.07] | 0.86 [0.74, 1.01], N=11,939 | a peer's night is an ordinary night for its options |
| E4 pinning | 2,772: close within USD 0.125 of a listed strike on the post-earnings expiry, minus adjacent sessions | +0.17 points [-1.24, +1.66], N=3,188 (2013-18) | +0.91 points [-0.32, +2.15], N=5,649 (2019-24) | cannot exclude a gap of about one point |
| E4 strike choice | 2,773: sell the strike among K-1, K0, K+1 with the most prior volume (open-interest proxy), megacap hedged hold | +0.057% of m0 [-0.161, +0.268], N=432, null percentile 46 | -0.071% of m0 [-0.199, +0.059], N=552, null percentile 25 | no historical open interest exists on disk; the proxy is unvalidated |
| E5 reversal | 2,802: So and Wang pre-announcement reversal, market-hedged | -0.013% [-0.420, +0.406], N=1,035 (2019-21) | +0.155% [-0.204, +0.521], N=1,315 (2022-24) | both legs rise; the long-short picks up only common drift |
| E5 premium | 2,803: long every reporter over the event window, market-hedged | +0.124% [-0.109, +0.358], N=2,736 | +0.037% [-0.181, +0.264], N=3,204 | published sign, about one stock round trip wide |
| E5 session | 2,805: select after-close reports on the hedged hold (Lyle et al. 2018) | +2.09% of premium in residual value [-1.96, +6.10], N=712, null 89 | +1.54% [-1.14, +4.20], N=1,955, null 77 | the paper's extra post-event variance is absent: -0.001 [-0.029, +0.028], N=4,485 |

E5 also scored 2,804 (option-expiration week, broad basket): -0.256% per week [-0.780, +0.253],
N=36 weeks on discovery, wrong sign; its held-out block was left unread.

Context figure, not a trial: on 2019-24 the hedged hold nets -1.05% of m0 per trade on all events
with a timed session label and -0.78% [-1.44, -0.13] on after-close events (E5,
`session_heldout.json`).

## Defects found

**2025-26 strike centring.** `outputs/research/oos_2026_ledger.csv` takes its entry and exit spot
from `earnings_iv_crush/research/chains.py::_spot_table`, which downloads dividend-adjusted closes
(`auto_adjust=True`), and `_straddle` picks the "at the money" strike against that spot. Against the
15:59 parity forward of the cached strike, the broad 2025-26 strike sits below the money by a mean
ln(F/K) of +188 bp (median +136 bp; 2025 Q1 +314 bp, 2026 Q2 +66 bp; N=1,220). The megacap panel,
built on an unadjusted spot, shows +17 bp, which is strike spacing. Three checks agree: E1's parity
forward against CRSP closes (+8.4 bp, N=239, the size of carry), the lead's sample of 153 events,
and E2's held-out build, where the strike nearest the forward is chosen on 33.9% of events against
74.2% on discovery. Consequences: the 2025-26 ledger sells an in-the-money call and an
out-of-the-money put, carries net short stock delta overnight, overstates `implied_move` by about
the gap and understates m0. Whether the 2025-26 headline figures move, and in which direction, is
not yet measured. The 2013-24 panels use CRSP and are not affected by this path.

**Ex-dividend credit in the hedged hold.** The hold keeps the short call through an ex-dividend
date inside the hold and settles on the raw close while the hedge earns total return
(`earnings_iv_crush/research/hedged_hold.py`, lines 461 to 475), so where early exercise is
optimal (D above the put value) the writer is credited with a dividend rational holders take. The
ex-date falls inside the hold on about 10% of broad events and exercise is optimal on about 4%.
Restated after review: H is overstated by up to about +0.08 to +0.11% of m0 per trade (2013-18
+0.110% [+0.088, +0.133]; 2019-24 +0.084% after excluding three special dividends that OCC
adjusts by strike rather than leaving to exercise). It is an upper bound because it assumes every
optimal exercise happens. The paper book is not exposed: `earnings_iv_crush/live/session.py`
(`exdiv_decision`) skips any event with a readable ex-date inside the hold.

**Unchecked class.** Whether the hedged-hold settlement uses the unadjusted strike on events where
OCC adjusted the contract for a special dividend of USD 12.50 or more. No study has checked it.

## Review corrections

The review's per-lane verdicts: E1 stands with corrections (already applied in its diagnosis.log
entry 7), E2 stands with corrections, E3 stands, E4 stands with corrections, E5 stands. Every
freeze note was written before its held-out log, and every scorer and note hash reproduces under
its stated convention (E2 after converting CRLF to LF; E4 excluding the blank line before the hash
line).

- E1 and E2 held-out blocks return clean only under new panel names; the same events carry the
  `hedged_event_hold 2025-26 *` row in `research/ledger/blocks.csv`. Both lanes disclose it. Read
  them as exploratory, not clean.
- E1 scored about 20 configurations behind 13 trial numbers (2,692 covers six rebalancing clocks;
  2,683 and 2,693 two or more each). Its m0 figures were corrected after the held-out read by a
  second computation on the same block (2,694); the debit-basis primary never used the spot. The
  "90 times the gross" ratio divides by a held-out gross whose interval spans zero; at the gross
  upper bound the touch is still about 33 times larger.
- E2 attributed the 2025-26 moneyness shift to a different strike rule; the cause is the adjusted
  spot above. Its outcomes are parity forwards, so the numbers stand. The like-for-like read is
  2,722 (near-the-money only, N=226, fail). Its signal was redesigned (delta weighting) after
  seeing held-out features but not outcomes, disclosed.
- E3 leaves 68 event-file tickers unmapped in the own-report exclusion, which would inflate the
  variance ratio; the ratio is below one regardless.
- E4: the ex-dividend sizing is restated above. Four figures in its `diagnosis.log` (median
  break-even non-assignment share 0.49, "31% of name-days", the USD 0.175 half-spread, "about a
  quarter above parity") trace to no result file, and "median 22 days" does not reproduce (19.5 on
  optimal events, 21 on all); none is cited here. The 2,772 per-grid and scale-free cuts were not
  declared; the USD 0.50 grid cut (+3.7 points [-0.04, +7.3]) is a lead for nothing.
- E5's pre-amendment discovery output was overwritten; the re-run primary matches the figures in
  its log.

## Trial accounting

43 trial numbers used: E1 13 (2,682 to 2,694, the last being the m0 re-computation), E2 11 (2,712 to
2,722), E3 13 (2,742 to 2,754, of which 2,748 abandoned unscored and 2,753 withdrawn), E4 2 (2,772
and 2,773), E5 4 (2,802 to 2,805). Unused reserved numbers are not trials. One
`exploratory-unhashed` row per lane is appended to `research/ledger/trials.csv` and 25 block views
to `research/ledger/blocks.csv` by `ledger_entries.py`.

## What is left

Nothing in these lanes warrants a forward test. The two defects are corrections to existing books:
re-strike the 2025-26 ledger on the 15:59 parity forward and re-score it as a new dated correction,
and add early assignment on the last cum-dividend day (or the live rule's ex-date exclusion) to the
hedged-hold valuation. The remaining untested ideas from E5's map are the dealer-gamma state from
customer-signed flow (needs an open/close-flagged feed the caches lack) and notice length of the
report date (needs first-seen dates in the calendar snapshots, unchecked).
