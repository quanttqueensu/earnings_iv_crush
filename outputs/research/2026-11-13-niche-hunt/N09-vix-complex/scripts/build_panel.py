"""build_panel.py: assemble the VX futures panel, index histories and event calendar for N09.

Writes to ``<lane>/data/``:
  * ``vx_panel.parquet``   one row per (trade_date, contract) with settle, close, volume, OI,
                           final settlement date;
  * ``indices.parquet``    VIX, VIX9D, VIX3M, VVIX closes by date;
  * ``events.csv``         scheduled FOMC statement days 2004-2026 plus CPI and NFP 2016-2026.

No outcome is computed here. Prints a funnel.

Usage
-----
    python -I scripts/build_panel.py <lane_dir> <repo_root>
"""

from __future__ import annotations

import datetime as dt
import re
import sys
from pathlib import Path

import pandas as pd

MONTHS = {
    m: i + 1
    for i, m in enumerate(
        [
            "January",
            "February",
            "March",
            "April",
            "May",
            "June",
            "July",
            "August",
            "September",
            "October",
            "November",
            "December",
        ]
    )
}
OLD_LAST_MONTH = 201312  # archive files used up to this contract month, current format after
FIRST_CONTRACT = 200701  # sample starts 2008; earlier archive files have malformed rows
PRE_2007_SCALE_END = pd.Timestamp("2007-03-26")  # VX quoted at 10x VIX before this date


def _rule_expiry(year: int, month: int) -> pd.Timestamp:
    ny, nm = (year + 1, 1) if month == 12 else (year, month + 1)
    first = dt.date(ny, nm, 1)
    third_fri = first + dt.timedelta(days=(4 - first.weekday()) % 7 + 14)
    return pd.Timestamp(third_fri - dt.timedelta(days=30))


def load_vx(raw: Path) -> pd.DataFrame:
    frames = []
    funnel = {"files": 0, "used": 0, "rows": 0}
    for f in sorted((raw / "vx").glob("*.csv")):
        funnel["files"] += 1
        kind, ym = f.stem.split("_")
        ym_i = int(ym)
        if ym_i < FIRST_CONTRACT or (kind == "old" and ym_i > OLD_LAST_MONTH) or (
            kind == "new" and ym_i <= OLD_LAST_MONTH
        ):
            continue
        # some 2013 archive files open with a one-line disclaimer before the header
        skip = 0 if f.read_text(errors="ignore").startswith("Trade Date") else 1
        d = pd.read_csv(f, index_col=False, skiprows=skip)
        d.columns = [c.strip() for c in d.columns]
        d["trade_date"] = pd.to_datetime(d["Trade Date"], format="mixed")
        d = d.rename(
            columns={
                "Open": "open",
                "High": "high",
                "Low": "low",
                "Close": "close",
                "Settle": "settle",
                "Total Volume": "volume",
                "Open Interest": "oi",
            }
        )
        for c in ("open", "high", "low", "close", "settle"):
            d[c] = pd.to_numeric(d[c], errors="coerce")
            d.loc[d["trade_date"] < PRE_2007_SCALE_END, c] /= 10.0
        d["contract"] = ym_i
        y, m = divmod(ym_i, 100)
        last = d["trade_date"].max()
        rule = _rule_expiry(y, m)
        # expired contracts: final row is the final settlement date; live ones: rule date
        d["expiry"] = last if last >= rule - pd.Timedelta(days=3) else rule
        frames.append(
            d[["trade_date", "contract", "expiry", "open", "high", "low", "close", "settle",
               "volume", "oi"]]
        )
        funnel["used"] += 1
        funnel["rows"] += len(d)
    out = pd.concat(frames, ignore_index=True)
    out = out[out["settle"] > 0].copy()
    print("vx funnel", funnel, "rows with settle>0", len(out))
    dup = out.duplicated(["trade_date", "contract"]).sum()
    if dup:
        raise ValueError(f"{dup} duplicate (trade_date, contract) rows")
    return out.sort_values(["trade_date", "expiry"]).reset_index(drop=True)


def load_indices(raw: Path) -> pd.DataFrame:
    cols = {}
    for s in ("VIX", "VIX9D", "VIX3M", "VVIX", "VIX1D"):
        d = pd.read_csv(raw / "indices" / f"{s}_History.csv")
        d["DATE"] = pd.to_datetime(d["DATE"], format="%m/%d/%Y")
        col = "CLOSE" if "CLOSE" in d.columns else s
        cols[s] = d.set_index("DATE")[col].astype(float)
    return pd.DataFrame(cols).sort_index()


def fomc_from_fed(raw: Path) -> list[pd.Timestamp]:
    out = []
    pat = re.compile(r"<h5[^>]*>([^<]*)</h5>")
    for f in sorted((raw / "fed").glob("fomchist_*.htm")):
        year = int(f.stem.split("_")[1])
        for h in pat.findall(f.read_text(encoding="utf-8", errors="ignore")):
            if "Meeting" not in h or "unscheduled" in h or "cancelled" in h:
                continue
            head = h.split(" - ")[0].replace("Meeting", "").strip()
            mon, days = head.split(" ", 1)
            mon_last = mon.split("/")[-1]
            # "July 31-August 1": the closing month sits inside the day range
            inner = [w for w in re.findall(r"[A-Za-z]+", days) if w[:3] in {k[:3] for k in MONTHS}]
            if inner:
                mon_last = inner[-1]
            day_last = int(re.split(r"[-\s]", days.strip())[-1].strip() or 0)
            month = next(v for k, v in MONTHS.items() if k.startswith(mon_last[:3]))
            out.append(pd.Timestamp(year, month, day_last))
    return sorted(set(out))


def main(lane: Path, repo: Path) -> None:
    raw = lane / "raw"
    data = lane / "data"
    data.mkdir(exist_ok=True)
    vx = load_vx(raw)
    vx.to_parquet(data / "vx_panel.parquet")
    idx = load_indices(raw)
    idx.to_parquet(data / "indices.parquet")
    fed = fomc_from_fed(raw)
    cal = pd.read_csv(repo / "data/cache/index_events/macro_releases_2016_2026.csv",
                      parse_dates=["date"])
    proj_fomc = set(cal.loc[cal["kind"] == "fomc", "date"])
    fed_set = set(fed)
    overlap = [d for d in fed_set if pd.Timestamp("2016-01-01") <= d <= pd.Timestamp("2020-12-31")]
    proj_overlap = {d for d in proj_fomc if d.year <= 2020}
    print("FOMC cross-check 2016-2020: fed", len(overlap), "project", len(proj_overlap),
          "fed-only", sorted(set(overlap) - proj_overlap), "project-only",
          sorted(proj_overlap - set(overlap)))
    fomc = sorted({d for d in fed_set if d.year <= 2020} | {d for d in proj_fomc if d.year >= 2021})
    ev = pd.concat(
        [
            pd.DataFrame({"date": fomc, "kind": "fomc"}),
            cal[cal["kind"].isin(["cpi", "nfp"])][["date", "kind"]],
        ]
    ).sort_values("date")
    ev.to_csv(data / "events.csv", index=False)
    print("events", ev.groupby("kind").size().to_dict(), "fomc years",
          pd.Series([d.year for d in fomc]).value_counts().sort_index().to_dict())


if __name__ == "__main__":
    main(Path(sys.argv[1]), Path(sys.argv[2]))
