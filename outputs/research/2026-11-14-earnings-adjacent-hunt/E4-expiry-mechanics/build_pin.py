"""
build_pin.py
E4 trial 2,772 inputs: per hedged-hold event, the listed strike grid of the front (post-earnings)
expiry from the reaction-session chain, and CRSP closes on the expiry session and on the control
sessions E-1, E+1, E+2. Writes ``pin_inputs.parquet``; computes no outcome statistic.

Usage
-----
    python outputs/research/2026-11-14-earnings-adjacent-hunt/E4-expiry-mechanics/build_pin.py
"""

from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

HERE = Path(__file__).resolve().parent
HH = ROOT / "outputs" / "research" / "2026-11-02-hedged-event-hold"
FEATURES = ROOT / "outputs" / "research" / "2026-10-20-hedged-hold" / "features.parquet"
CRSP = ROOT / "outputs" / "research" / "2026-10-20-hedged-hold" / "crsp_paths.parquet"
CHAINS = ROOT / "data" / "cache" / "backfill_chains"
STRIPS = ROOT / "data" / "processed" / "databento_quotes"


# ── strike grids ────────────────────────────────────────────────────────────


def grid_broad(ticker: str, day: pd.Timestamp, expiry: pd.Timestamp) -> np.ndarray | None:
    p = CHAINS / f"{ticker}_{day.date()}.parquet"
    if not p.exists():
        return None
    d = pd.read_parquet(p, columns=["symbol"]).reset_index()
    body = d["symbol"].astype(str).str.replace(" ", "", regex=False).str[-15:]
    exp = pd.to_datetime(body.str[:6], format="%y%m%d", errors="coerce")
    k = pd.to_numeric(body.str[7:], errors="coerce") / 1000.0
    ks = np.unique(k[(exp == expiry) & k.notna()].to_numpy(float))
    return ks if ks.size else None


def grid_megacap(ticker: str, day: pd.Timestamp, expiry: pd.Timestamp) -> np.ndarray | None:
    p = STRIPS / ticker / f"{day.date()}_chain.parquet"
    if not p.exists():
        return None
    d = pd.read_parquet(p, columns=["expiry", "strike"])
    ks = np.unique(d.loc[pd.to_datetime(d["expiry"]) == expiry, "strike"].to_numpy(float))
    return ks if ks.size else None


def main() -> None:
    f = pd.read_parquet(FEATURES, columns=["ticker", "entry_date", "permno"])
    f["entry_date"] = pd.to_datetime(f["entry_date"])
    f = f.drop_duplicates(["ticker", "entry_date"])
    c = pd.read_parquet(CRSP, columns=["permno", "date", "prc", "cfacpr"])
    c["date"] = pd.to_datetime(c["date"])
    c["prc"] = pd.to_numeric(c["prc"], errors="coerce").abs()
    panels = {int(k): g.set_index("date").sort_index() for k, g in c.groupby("permno")}

    rows, funnel = [], Counter()
    for panel, fname, gridf in (
        ("broad", "events.parquet", grid_broad),
        ("megacap", "events_megacap.parquet", grid_megacap),
    ):
        ev = pd.read_parquet(HH / fname)
        ev = ev[ev["status"] == "ok"].copy()
        for col in ("entry_date", "exit_date", "expiry"):
            ev[col] = pd.to_datetime(ev[col])
        ev = ev.merge(f, on=["ticker", "entry_date"], how="left")
        funnel[f"{panel}_events_ok"] += len(ev)
        for _, e in ev.iterrows():
            base = {"panel": panel, "ticker": e["ticker"], "entry_date": e["entry_date"],
                    "exit_date": e["exit_date"], "expiry": e["expiry"], "K0": e["strike"]}
            if not np.isfinite(e["permno"]) or int(e["permno"]) not in panels:
                funnel[f"{panel}_no_permno"] += 1
                continue
            g = panels[int(e["permno"])]
            sess = g.index
            i_e = int(np.searchsorted(sess, e["expiry"], side="right")) - 1
            if i_e < 0 or i_e + 2 >= len(sess):
                funnel[f"{panel}_no_sessions"] += 1
                continue
            ks = gridf(e["ticker"], e["exit_date"], e["expiry"])
            if ks is None:
                funnel[f"{panel}_no_reaction_grid"] += 1
                continue
            day = {"E": sess[i_e], "Em1": sess[i_e - 1], "Ep1": sess[i_e + 1], "Ep2": sess[i_e + 2]}
            out = {**base, "expiry_session": day["E"], "n_grid": int(ks.size),
                   "grid_lo": float(ks.min()), "grid_hi": float(ks.max())}
            cf = g["cfacpr"].iloc[i_e - 1 : i_e + 3]
            out["split_near"] = bool(cf.nunique() > 1)
            for lab, dd in day.items():
                p = float(g.at[dd, "prc"])
                out[f"close_{lab}"] = p
                if np.isfinite(p):
                    j = np.abs(ks - p).argmin()
                    out[f"dist_{lab}"] = float(abs(ks[j] - p))
                    out[f"nearest_{lab}"] = float(ks[j])
                    # local spacing: gap between the two listed strikes around the close
                    lo, hi = ks[ks <= p], ks[ks > p]
                    out[f"spacing_{lab}"] = (
                        float(hi.min() - lo.max()) if lo.size and hi.size else np.nan
                    )
                    out[f"inside_{lab}"] = bool(lo.size and hi.size)
            out["em1_after_reaction"] = bool(day["Em1"] > e["exit_date"])
            rows.append(out)
            funnel[f"{panel}_built"] += 1
    d = pd.DataFrame(rows)
    d.to_parquet(HERE / "pin_inputs.parquet")
    print("funnel:", dict(funnel))
    print("rows", len(d))


if __name__ == "__main__":
    main()
