# Pre-registration: resting entry on an unseen block (confirmation of 53aa4898, plus a pegged variant)

Frozen before any tick for the declared block is pulled. Changes after an outcome is viewed require a
dated amendment with its own hash. Record:
`outputs/research/prereg_2026-11-13-maker-entry-confirmation.json`. Scorer:
`research/execution/2026-11-13-maker-entry-confirmation/study.py`.

## Hypothesis

Trial A (1,629). Resting each straddle leg at the 15:00 mid and selling unfilled legs at the 15:59:00
bid improves the entry price over selling both legs at the 15:59:00 bid: mean improvement per event,
in units of m0, is positive with a date-clustered interval excluding zero and t of at least 3.

Trial B (1,630). Re-pegging each leg to the current mid every minute from 15:00 to 15:44 and selling
unfilled legs at the 15:45:00 bid improves the entry price over selling both legs at the 15:45:00
bid, under the same criterion.

## Mechanism

Liquidity takers in single-name options pay the touch: on this project's prints the median price
improvement inside the spread is 0.0% (34,672 prints, `docs/SYSTEM.md`), and option half-spreads in
the last hour before an after-close print are wide (measured entry half-spread 1.79% of premium at
15:59 on the fixed-time basis). A sell order resting at the mid is filled when buyers lift it or the
bid moves up to it, so a seller who can wait collects part of the half-spread a taker gives away.
Muravyev (Journal of Finance 2016) finds the inventory component of option price impact larger than
the asymmetric-information component, the condition under which resting liquidity earns the spread
rather than being picked off. The risk is the opposite channel: volatility-informed buying before
earnings (Ni, Pan and Poteshman, Journal of Finance 2008) and stale limits traded through when the
stock moves. Both are inside the statistic. Every event is sold in both arms, so the position and
its event outcome are identical, and a fill that is picked off shows up as a limit below the later
bid, a negative contribution. Trial B's re-pegging is meant to remove the stale-limit component that
W1's markouts showed arriving within one minute of a fill.

## Data and blocks

- Events: every event in `outputs/research/2026-11-02-hedged-event-hold/events.parquet` with entry
  date 2023-03-28 (the first `cmbp-1` date) to 2024-12-31 and hedged-hold status `ok`: 1,712 events
  on 266 entry dates, 276 tickers. Only the columns ticker, entry date, expiry, status, strike and
  m0 are read; no outcome column is opened. The contract is the hedged hold's front at-the-money
  straddle (strike and expiry from that file).
- Unit: m0 from the same file (0.20 times the forward plus the entry bid, the hedged-hold margin
  unit). Study 53aa4898 rebuilt m0 from tick bids; here the chain-based value is used as frozen.
- Ticks: Databento OPRA `cmbp-1` for the two contracts of each event, entry session 14:55 to 16:00
  ET, one request per event, cached in `data/cache/flow/broad_2023_2024/`. The pull writes a
  SHA-256 manifest, and the scorer refuses any file that differs from it. Cost: priced with the
  vendor's free cost call before the freeze (figure in the trial accounting), hard cap USD 10.
- One block, confirmation_2023_2024. Resting-order fills have never been measured on it: W1 used
  broad 2025-26 and megacap 2023-24 (no ticker overlap with this block, checked), 53aa4898 used broad
  2025-26. What has been viewed on these events: the hedged-hold outcome H (2019-24 discovery, not
  used here) and fixed-time touch spreads in the cost studies, which are the baseline arm's price,
  not the resting fill.
- The status filter is not outcome-dependent: within the window, status `ok` excludes exactly the
  243 events of the 42 W1 megacap tickers (status `no_front_quote`) and one `no_hedge_vol`. It is
  what makes "no ticker overlap with W1" true.
- Prior pulls on these events: `outputs/research/2026-11-10-entry-time-descriptive/pull_1545.py`
  pulled 15:45 `cbbo-1m` chains for 729 of them for the entry-clock work. No resting-fill outcome
  was computed from them and the block ledger has no row for them; they are not used here.
- Differences from 53aa4898, none of them swept: the pull starts at 14:55, so an event whose leg
  has no record between 14:55 and 15:00 is excluded here (on 53aa4898's files 16 of 1,136 events,
  1.4%, would have been, a loss of N without a sign bias); m0 is the hedged-hold file's chain-based
  value rather than one rebuilt from tick bids; the contract is the hedged hold's front straddle.
- Exclusions, each counted in the printed funnel, separately per trial (an event that fails only
  one trial's quote requirement stays in the other): no tick file or an empty one, an early-close entry
  session, a leg with no two-sided quote at 15:00 (A and B), at 15:59:00 (A) or at 15:45:00 (B).

## Specification

Trial A, copied from 53aa4898. Per leg: limit is the mid of the last two-sided quote at or before
15:00:00, rounded down to the penny-programme tick (0.01 below 3.00, 0.05 at or above). Fill rule
strict: the first moment in [15:00:00, 15:59:00] that a trade prints above the limit or the NBBO bid
reaches it; the fill price is the limit. An unfilled leg sells at the last two-sided bid at or before
15:59:00. Improvement per event is the sum over filled legs of (limit minus the 15:59:00 bid),
divided by m0.

Trial B. Per leg, at the start of each minute from 15:00 to 15:44 the limit is reset to the current
mid rounded down as in A (carried forward if no quote is present). The order fills within that
minute under the strict rule at that minute's limit. An unfilled leg sells at the 15:45:00 bid.
Improvement per event is the sum over filled legs of (fill limit minus the 15:45:00 bid), divided
by m0. The 15:45 baseline is the entry clock the book now uses; its parameters (one-minute re-peg,
15:45 stop) are taken from the liquidity-provider report of 2026-11-13, not swept.

Trial B's minutes are half-open, [m:00, m+1:00), so every record from 15:00:00 to 15:44:59.999 is
tested exactly once.

No feature, threshold or quantile is estimated from data. Fills use only ticks up to the fill
time. One look-ahead is inherited from 53aa4898 and is not removed, to keep trial A an exact
replication: the strike is the listed strike nearest the 15:59 parity forward
(`earnings_iv_crush/research/hedged_hold.py`, via the hedged-hold feature build), while the order
rests from 15:00. Choosing the strike with 15:59 information makes the straddle more nearly
at-the-money at the baseline time than at 15:00, which to second order favours the resting arm; a
rough size is 0.001 of m0, half the detectable effect and about a tenth of 53aa4898's. Every pass
is therefore an upper bound, for this reason and for the fill-model reasons below. A diagnostic
is declared for it: trial A's mean improvement by tercile of the 15:00 parity offset
|C mid minus P mid| / m0, reported and never a criterion.

## Primary statistic and inference

Per trial, the mean improvement per event in units of m0, per trade, gross of commission (the
commission is the same in both arms). Date-clustered 95% percentile bootstrap on entry dates (5,000
draws, seed 0, `protocol.date_clustered_ci`), the bootstrap p-value (`date_clustered_pvalue`), and
t as the mean over its CR1 date-clustered standard error. No matched random null: this is not a
selector, and every event is traded in both arms.

Reported beside the primary, never as a criterion, and only in the unblinded run: the same mean
under a quote-only fill rule (the order fills only when the NBBO bid reaches the limit, prints
ignored), whose gap from the strict mean is the main audit of the print-based rule (OPRA here has
no condition codes, so complex-order legs and auction prints count as strict fills); the split of
each filled leg's improvement into drift (limit minus the baseline mid) and half-spread (baseline
mid minus baseline bid), to confirm the half-spread is the driver; the both-leg and any-leg fill
rates; the parity-offset terciles above; and the count of strict fills triggered by a print above
the prevailing ask. Blind development runs print the primary on sign-flipped values only.

## Power

From 53aa4898's scored file (broad 2025-26, already viewed): the per-event improvement had SD 0.0205
of m0 and a date-clustered standard error of 0.00062 at N 1,136 on 192 dates. Scaling by the square
root of N, the standard error at about 1,650 scored events is near 0.0005, so a mean of 0.0019 of m0
is detected with 80% power at t of 3 ((3 + 0.84) times 0.0005). The effect 53aa4898 found was 0.0089
for trial A's rule; the mechanism implies trial B's effect is smaller, because the 15:45 half-spread
is narrower than 15:59's and re-pegging gives back queue time, plausibly 0.003 to 0.006. Both lie
above the detectable size. The statistic can answer the question whatever the book's sign: it is a
paired price difference on identical positions, not a ratio of a negative-mean book.

## Block history

The ledger check below is empty by construction, because `broad_entry_ticks` is a new panel name
and `block_is_clean` matches names exactly. The real evidence of cleanliness is the cache scan done
in the pre-freeze review: no tick file for any of the 1,712 events exists under `data/cache` or
`data/processed/databento`, and the pre-ledger closed list has no resting-order study on this block.

`protocol.block_is_clean(LEDGER, panel="broad_entry_ticks", period="2023-03-28..2024-12-31",
outcome_family="entry_execution", feature_family=...)` returns clean for both `resting_static_mid`
and `resting_pegged_mid`, with no rows. The ledger begins at trial 1,593; the closed list in
`docs/RESEARCH_STATE.md` was read for earlier resting-order work and none used this block.

## Success criterion

For each trial: mean improvement greater than zero with the date-clustered 95% interval excluding
zero, t of at least 3, and its p-value passing Benjamini-Hochberg at 5% across the two trials. The
LOND alpha is recorded beside each trial in `research/ledger/trials.csv` as advisory
(`docs/PROTOCOL.md` P20). Trial A passing confirms 53aa4898 on an unseen block. One block, so
scoring has one stage.

## Kill criterion

Trial A failing closes the resting-entry lever for the paper book as specified in 53aa4898: the
2025-26 pass is then read as a product of a block partly seen. Trial B failing closes re-pegging at
a one-minute cadence. A pass under the strict rule with a quote-only mean whose interval reaches
zero is reported as "passes only under the print-based fill rule", which cannot be promoted to the
paper book without real fills. No split (by spread, implied move or ticker) can rescue a failure.

## Nearest closed studies

- "Resting orders (maker F1)" (`docs/RESEARCH_STATE.md`, `execution/findings/flow_liquidity.md`):
  static 15:00 mid, cross at 15:59:59, one-night book, judged by a 5-minute markout gate. Failed
  the gate in both blocks. This study scores the paired price improvement on identical positions,
  where the markout is inside the statistic, on a block F1 never touched.
- "Better fills on the fixed 15:59 book": execution improvements on the taker book at fixed times,
  worth about +0.007 Sharpe. That work changed the price paid when crossing; this one replaces the
  cross with a resting order and crosses only what does not fill.
- 53aa4898 itself is entered in `docs/RESEARCH_STATE.md` with these trials.

## Trial accounting

Two trials, 1,629 (A) and 1,630 (B), one slate. LOND indices 1 and 2 under the new regime, advisory
alphas 0.0304 and 0.0076. Count after this study: 1,630. Pull estimate: USD 0.1844 for 1,712 requests (vendor `get_cost`, 2026-11-13), cap USD 10.
