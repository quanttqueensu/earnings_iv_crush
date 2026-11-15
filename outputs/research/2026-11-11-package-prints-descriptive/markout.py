"""markout.py: straddle mid after package prints on the entry day (descriptive, not a trial).

For each straddle-candidate package print from ``describe.py``, the summed mid of the two legs at
the print and 1, 5 and 15 minutes later, from the same tick file. Prints below the package mid are
read as seller-side. ``cost`` is (mid at print - price) / mid at print; ``drift`` is the later mid
minus the mid at print, same unit. A seller-side print followed by a rising mid was picked off.

Usage
-----
    python outputs/research/2026-11-11-package-prints-descriptive/markout.py
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow.parquet as pq

ROOT = Path(__file__).resolve().parents[3]
FLOW = ROOT / "data" / "cache" / "flow"
OUT = Path(__file__).resolve().parent
HORIZONS_MIN = (1, 5, 15)
SIDE_BAND = 0.05  # prints within this of the package mid are unsigned


def _mids(path: Path) -> dict[str, pd.DataFrame]:
    q = pq.read_table(path, columns=["ts_event", "symbol", "bid_px_00", "ask_px_00"]).to_pandas()
    q = q[(q["bid_px_00"] > 0) & (q["ask_px_00"] > q["bid_px_00"])]
    q["mid"] = (q["bid_px_00"] + q["ask_px_00"]) / 2
    q["right"] = q["symbol"].str.strip().str[-9]
    return {r: g[["ts_event", "mid"]].sort_values("ts_event") for r, g in q.groupby("right")}


def main() -> None:
    p = pd.read_parquet(OUT / "packages.parquet")
    p = p[(~p["synthetic"]) & (p["leg"] == "pre")].copy()
    rows = []
    for (block, ticker, date), g in p.groupby(["block", "ticker", "date"]):
        m = _mids(FLOW / block / f"{ticker}_{date}_pre.parquet")
        if set(m) != {"C", "P"}:
            continue
        g = g.sort_values("ts_event")
        close = g["ts_event"].dt.tz_convert("America/New_York").dt.normalize() + pd.Timedelta(
            hours=15, minutes=59
        )
        out = g[["block", "ticker", "date", "ts_event", "size", "pkg_loc", "half_spread_rel"]].copy()
        for h in (0, *HORIZONS_MIN):
            t = pd.DataFrame({"ts_event": g["ts_event"] + pd.Timedelta(minutes=h)})
            ok = (t["ts_event"] <= close.dt.tz_convert("UTC")).to_numpy()
            tot = np.zeros(len(g))
            for r in ("C", "P"):
                tot += pd.merge_asof(t.sort_values("ts_event"), m[r], on="ts_event")["mid"].to_numpy()
            out[f"mid{h}"] = np.where(ok, tot, np.nan)
        rows.append(out)
    d = pd.concat(rows, ignore_index=True)
    d["side"] = np.where(d["pkg_loc"] < 0.5 - SIDE_BAND, "seller-side",
                         np.where(d["pkg_loc"] > 0.5 + SIDE_BAND, "buyer-side", "at mid"))
    d["cost"] = (d["pkg_loc"] - 0.5).abs() * 2 * d["half_spread_rel"]
    for h in HORIZONS_MIN:
        d[f"drift{h}"] = d[f"mid{h}"] / d["mid0"] - 1
    d.to_parquet(OUT / "markout.parquet")
    et = d["ts_event"].dt.tz_convert("America/New_York")
    d["late"] = et.dt.time >= pd.Timestamp("15:30").time()

    def summarise(g: pd.DataFrame) -> pd.Series:
        ev = g.groupby(["ticker", "date"])[["cost", "drift1", "drift5", "drift15"]].mean()
        rng = np.random.default_rng(0)
        res = {"events": len(ev), "prints": len(g)}
        for c in ev.columns:
            v = ev[c].dropna()
            b = [v.sample(len(v), replace=True, random_state=rng).mean() for _ in range(2000)]
            res[c] = f"{100 * v.mean():+.2f} [{100 * np.percentile(b, 2.5):+.2f}, {100 * np.percentile(b, 97.5):+.2f}]"
        return pd.Series(res)

    pd.set_option("display.width", 250)
    print("Percent of the straddle mid at the print; event-equal means, event bootstrap 95%.")
    print("cost = distance of the print from the mid; drift = later mid minus mid at the print.")
    print("\nAll session")
    print(d.groupby(["block", "side"]).apply(summarise).to_string())
    print("\n15:30 to 15:59 ET only")
    print(d[d["late"]].groupby(["block", "side"]).apply(summarise).to_string())
    big = d[d["late"] & (d["size"] >= 5)]
    print("\n15:30 to 15:59 ET, 5 lots or more")
    print(big.groupby(["block", "side"]).apply(summarise).to_string())
    n_ev = d[d["late"] & (d["side"] == "seller-side")].groupby("block").apply(
        lambda g: g.groupby(["ticker", "date"]).ngroups)
    print("\nevents with at least one seller-side package print 15:30-15:59:", n_ev.to_dict(),
          "of", {b: len(list((FLOW / b).glob("*_pre.parquet"))) for b in d["block"].unique()})


if __name__ == "__main__":
    main()
