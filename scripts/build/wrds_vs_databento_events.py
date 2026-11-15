"""
wrds_vs_databento_events.py
Reconcile the WRDS-sourced calendar against the live Databento/Finnhub one.

Quantifies what re-sourcing the calendar off WRDS buys, and catches linking errors before the
WRDS set is trusted. Three comparisons on the shared 50-name / 2019-2024 scope:

  1. announce date - exact and +/-1 business-day agreement, plus events only one source carries;
  2. session (bmo/amc) - agreement on the matched pairs (WRDS ``dmh`` folded to bmo, since the
     entry/exit logic treats a during-hours print like a before-open one);
  3. spot - CRSP as-traded close (``dsf`` ``|prc|``, same unadjusted basis as yfinance
     ``auto_adjust=False``) at each marked event's entry/exit against the yfinance
     ``spot_entry``/``spot_exit`` already in the Databento event set.

Read-only; no Databento credits spent. Reads calendar_wrds.parquet (from build_wrds_events.py),
calendar_databento.parquet and events_megacap_databento.parquet.

Run: ``python scripts/build/wrds_vs_databento_events.py``
"""

from __future__ import annotations

import datetime as dt
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from earnings_iv_crush.data import wrds_r2 as w  # noqa: E402

WRDS_CAL = Path("outputs/research/calendar_wrds.parquet")
DBO_CAL = Path("outputs/research/calendar_databento.parquet")
DBO_EVENTS = Path("outputs/research/events_megacap_databento.parquet")


def _eff(session: str) -> str:
    """Effective session for the entry/exit logic: a during-hours print acts like bmo."""
    return "bmo" if session == "dmh" else session


def _match_calendars(wr: pd.DataFrame, db: pd.DataFrame) -> pd.DataFrame:
    """Nearest-date pairing of WRDS and Databento events within a name."""
    rows = []
    for tic, dbg in db.groupby("ticker"):
        wrg = wr[wr["ticker"] == tic]
        db_dates = np.sort(dbg["announce_date"].values)
        wr_dates = np.sort(wrg["announce_date"].values)
        for d in db_dates:
            if len(wr_dates):
                gap_days = np.min(np.abs((wr_dates - d) / np.timedelta64(1, "D")))
            else:
                gap_days = np.nan
            rows.append({"ticker": tic, "db_date": d, "gap_days": gap_days})
    return pd.DataFrame(rows)


def _spot_recon(wr: pd.DataFrame, ev: pd.DataFrame) -> None:
    """CRSP as-traded close vs the event set's yfinance spot at entry and exit."""
    # cusip8 -> permno via CRSP names (effective-dated; take the row covering the window)
    cusip8s = sorted(wr["cusip8"].dropna().unique())
    nm = w.read_table(
        "crsp_a_stock",
        "dsenames",
        columns=["permno", "ncusip", "ticker", "namedt", "nameendt"],
        filters=[("ncusip", "in", cusip8s)],
    )
    c2p = (
        nm.sort_values("nameendt")
        .drop_duplicates("ncusip", keep="last")
        .set_index("ncusip")["permno"]
    )
    tic2cusip = wr.drop_duplicates("ticker").set_index("ticker")["cusip8"]
    ev = ev.copy()
    ev["permno"] = ev["ticker"].map(tic2cusip).map(c2p)
    ev = ev[ev["permno"].notna()]
    permnos = sorted(int(p) for p in ev["permno"].unique())

    px = w.read_table(
        "crsp_a_stock",
        "dsf",
        columns=["permno", "date", "prc"],
        filters=[
            ("permno", "in", permnos),
            ("date", ">=", dt.date(2018, 12, 1)),
            ("date", "<=", dt.date(2025, 1, 15)),
        ],
    )
    px["date"] = pd.to_datetime(px["date"])
    # CRSP prc is negative when it is a bid/ask midpoint (no trade); use abs. Unadjusted
    # close = |prc|; the raw daily close matches an unadjusted quote source like yfinance's
    # as-traded price on that date, so compare raw close to raw spot.
    px["close"] = px["prc"].abs()
    px = px.set_index(["permno", "date"]).sort_index()

    def crsp_close(permno: float, day: pd.Timestamp) -> float:
        try:
            s = px.loc[int(permno)]
        except KeyError:
            return np.nan
        s = s[s.index <= day]
        return float(s["close"].iloc[-1]) if not s.empty else np.nan

    diffs = []
    for r in ev.itertuples(index=False):
        for day, spot in ((r.entry_date, r.spot_entry), (r.exit_date, r.spot_exit)):
            c = crsp_close(r.permno, pd.Timestamp(day))
            if c == c and spot == spot and spot:
                diffs.append(abs(c - spot) / spot)
    diffs = np.array(diffs)
    within = (diffs <= 0.005).mean() if len(diffs) else float("nan")
    print(
        f"\nspot (CRSP vs yfinance): n={len(diffs)} marks, median |diff| {np.median(diffs):.3%}, "
        f"{within:.0%} within 0.5%"
    )
    print(f"  names priced from CRSP: {ev['permno'].nunique()}/{ev['ticker'].nunique()}")


def main() -> None:
    wr = pd.read_parquet(WRDS_CAL)
    db = pd.read_parquet(DBO_CAL)
    wr["announce_date"] = pd.to_datetime(wr["announce_date"])
    db["announce_date"] = pd.to_datetime(db["announce_date"])
    print(
        f"WRDS calendar {len(wr)} events / {wr['ticker'].nunique()} names; "
        f"Databento {len(db)} / {db['ticker'].nunique()}"
    )

    m = _match_calendars(wr, db)
    exact = (m["gap_days"] == 0).mean()
    one = (m["gap_days"] <= 1).mean()
    far = m[m["gap_days"] > 1]
    print(
        f"\nannounce date: {exact:.0%} exact, {one:.0%} within 1 bday "
        f"({len(far)} Databento events > 1 day from any WRDS event)"
    )
    if len(far):
        print(far.sort_values("gap_days", ascending=False).head(8).to_string(index=False))

    # session agreement on exact-date pairs
    dbk = db.assign(key=db["ticker"] + "|" + db["announce_date"].dt.strftime("%Y-%m-%d"))
    wrk = wr.assign(key=wr["ticker"] + "|" + wr["announce_date"].dt.strftime("%Y-%m-%d"))
    j = dbk.merge(
        wrk[["key", "session", "session_source"]], on="key", suffixes=("_db", "_wr"), how="inner"
    )
    j["agree"] = j["session_db"].map(_eff) == j["session_wr"].map(_eff)
    print(
        f"\nsession: {len(j)} same-date pairs, {j['agree'].mean():.0%} agree "
        f"(disagreements below are where the Finnhub bmo/amc flag differs from IBES timing)"
    )
    dis = j[~j["agree"]]
    if len(dis):
        tab = dis.groupby([dis["session_db"], dis["session_wr"]]).size()
        print("  db_session -> wr_session counts:", tab.to_dict())

    _spot_recon(wr, pd.read_parquet(DBO_EVENTS))


if __name__ == "__main__":
    main()
