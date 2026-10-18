# Amendment 01 to the post-earnings pre-registration

Amends `_private/postea_prereg.md`, SHA-256
`bc22613afd90e0dc143ddc4b416761a52fc37bc3541b4b6fda97592a0645ae3d`, 10,154 bytes.

Frozen before any straddle is priced. Nothing in the estimand, the two control definitions,
the frozen DTE strata, the exclusions, the inference plan or the decision rule changes. Only
the price source changes, and it changes because the original source was measured and found
to fail in a way that would have biased the comparison.

## 1. Why the free feed is abandoned

Section 3 specified the free DoltHub chain database. Direct probe shows its coverage is
**date-dependent as well as name-dependent**. A fixed 18-name sample drawn from the study
universe, tested on one mid-June session per year:

| Year | Names resolving |
|---|---|
| 2019 | 0 / 18 |
| 2020 | 8 / 18 |
| 2021 | 9 / 18 |
| 2022 | 10 / 18 |
| 2023 | 10 / 18 |
| 2024 | 11 / 18 |

Overall coverage of the study universe is 14 of 40 on a 2022 session. Individual names enter
and leave: ON and PCG return nothing in 2021 and 2022 and full chains in 2023.

This is disqualifying for this design specifically, not merely inconvenient. Control A is
drawn on a different date from its event by construction, so a name covered in one year and
not another has its event priced and its control dropped, or the reverse. The resulting
attrition is correlated with date, date is correlated with volatility regime, and the
surviving matched pairs would be selected on the exact axis the comparison runs along. A
12-event smoke test lost all 12 control-B observations to this.

No result was computed on the free feed. Nothing is discarded because nothing was produced.

## 2. New price source

OPRA `cbbo-1m` consolidated quotes through Databento, marked at the last bar at or before
15:59 ET, which is the mark convention the rest of this project already uses and the one its
34,672-print execution study measured against.

This is strictly better for the test rather than merely available:

* coverage is complete from 2013, so the date-dependent attrition disappears entirely;
* both sides of the quote are genuine, so the bid-side entry section 4 requires is a real
  bid rather than a proxy for one.

The sample window is **unchanged** at 2019-01-01 to 2024-10-31 even though the new source
does not require the October 2024 cut-off. Comparability with the settled negative and with
the execution study is worth more here than five extra months.

## 3. Cost control

Metered source, so the following bind:

* measured rates from the free `metadata.get_cost` endpoint on real symbol lists:
  $0.00633 per underlying-session for `cbbo-1m` on a filtered ATM list averaging 109
  contracts, falling to about 8.3% of that when the request is restricted to the last 30
  minutes of the session, plus $0.00204 per name-day for the `definition` schema needed to
  enumerate contracts;
* estimated total for the pre-registered 1,200 events across three arms: **$9.25**;
* **hard cap $15**, enforced inside the pull loop against the exact pre-pull charge returned
  by the cost endpoint, not against an assumed rate. The run halts on reaching it and
  reports the achieved N rather than continuing;
* running spend printed throughout, and estimate against actual reconciled at the end.

Every request window is constructed by localising to `America/New_York` and converting,
never by string concatenation, so the offset follows daylight saving. This is not a
stylistic preference: passing timezone-naive stamps to this API once made this project
measure 11:30 to 12:00 and label it 15:59, and the intraday windowing that makes this study
affordable is the same mechanism.

## 4. What is unchanged

Estimand, both control estimands and the rule that they are reported separately and never
combined; the frozen DTE strata S1, S2 and S3; the matching variables and the requirement
that match quality is reported before any return is read; every exclusion and the requirement
that each reports a funnel count; event-level clustered inference and the calendar-time
portfolio, with the per-trade and annualised Sharpe never compared as if they were the same
number; the decision rule, including that failure under both controls closes single-name
earnings volatility; and the trial accounting of one trial against 1,477.

The 1,200-event sample size is unchanged. It was set by the free feed's per-query cost and
is retained under the new source so the sample is not chosen after the price of data changed.
