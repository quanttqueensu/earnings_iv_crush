"""Per-name session (bmo/amc) corrections confirmed against the WRDS/IBES calendar.

``scripts/wrds_vs_databento_events.py`` found 49 date/session disagreements between
the Finnhub/Yahoo-derived calendar and WRDS Compustat/IBES on the shared 50-name,
2019-2024 scope. 22 of those are exact-date session (bmo/amc) mismatches concentrated
in two names, GE and LIN, each disagreeing in the same direction every quarter for a
multi-year stretch -- a systematic labelling-convention difference, not scattered
noise. WRDS/IBES is treated as the more reliable source for session timing (it is a
point-in-time analyst-service field, not a scraped press-release heuristic).

Verified directly: repricing GE's flagged events on the WRDS-corrected entry date
(free DoltHub chains, ``_ge_lin_corrected_session_events.parquet``) collapses GE's
mean ``iv_term_spread`` from 0.52 (10 flagged events, wrong session) to 0.15 (near the
pool-wide average of ~0.18-0.20) and its ``causal_expanding_gate`` pass rate from
62.5% to 29.2%. One GE date (2019-01-31) has no DoltHub coverage and cannot be
verified this way; it is included here anyway since the underlying WRDS disagreement
is the same kind of evidence as its ten neighbours.

Only the 22 exact-date SESSION mismatches are covered here. Three separate LIN DATE
mismatches (WRDS announce date shifted by 1-17 days from Databento's) are a different
problem and are not corrected by this table.
"""

from __future__ import annotations

import pandas as pd

# (ticker, announce_date "YYYY-MM-DD") -> WRDS/IBES-confirmed session.
WRDS_SESSION_OVERRIDES: dict[tuple[str, str], str] = {
    ("GE", "2019-01-31"): "amc",
    ("GE", "2019-04-30"): "amc",
    ("GE", "2019-07-31"): "amc",
    ("GE", "2019-10-30"): "amc",
    ("GE", "2020-01-29"): "amc",
    ("GE", "2020-04-29"): "amc",
    ("GE", "2020-07-29"): "amc",
    ("GE", "2020-10-28"): "amc",
    ("GE", "2021-01-26"): "amc",
    ("GE", "2021-04-27"): "amc",
    ("GE", "2021-07-27"): "amc",
    ("LIN", "2019-08-05"): "amc",
    ("LIN", "2019-11-12"): "amc",
    ("LIN", "2020-02-13"): "amc",
    ("LIN", "2020-05-07"): "amc",
    ("LIN", "2021-02-05"): "amc",
    ("LIN", "2021-05-06"): "amc",
    ("LIN", "2022-02-10"): "amc",
    ("LIN", "2022-04-28"): "amc",
    ("LIN", "2022-07-28"): "amc",
    ("LIN", "2022-10-27"): "amc",
    ("LIN", "2023-02-07"): "amc",
}


def apply_session_overrides(
    calendar: pd.DataFrame,
    overrides: dict[tuple[str, str], str] | None = None,
) -> pd.DataFrame:
    """Overwrite ``session`` for rows matching a confirmed (ticker, date) correction.

    Marks corrected rows' ``session_source`` as ``"wrds_override"`` (column added if
    absent) so the correction stays traceable. No-op for rows that don't match.
    """
    overrides = WRDS_SESSION_OVERRIDES if overrides is None else overrides
    out = calendar.copy()
    if "session_source" not in out.columns:
        out["session_source"] = pd.NA
    dates = pd.to_datetime(out["announce_date"]).dt.strftime("%Y-%m-%d")
    for (ticker, date_str), session in overrides.items():
        mask = (out["ticker"] == ticker) & (dates == date_str)
        out.loc[mask, "session"] = session
        out.loc[mask, "session_source"] = "wrds_override"
    return out
