"""
score_pilot_a.py
Pilot A of lane N10 (exploratory, declared underpowered): short ATM straddle on the first
Deribit expiry after each crypto-native catalyst (halvings, Taproot, Ethereum forks, spot ETF
decisions), entered two hours before, against the same clock time one and two weeks earlier.
Also the DVOL change across each catalyst against the same controls (trial 2,371).

Usage:
    python outputs/research/2026-11-13-niche-hunt/N10-crypto-scheduled/score_pilot_a.py
"""

from __future__ import annotations

import csv
from datetime import datetime, timezone

import numpy as np
import pandas as pd
from n10lib import CACHE, HERE, delivery_prices, mean_ci, straddle
from pull_deribit import CATALYST_LEAD, CATALYSTS, CONTROL_WEEKS_A

EXPIRY_BUFFER = pd.Timedelta(hours=1)
DVOL_PRE = pd.Timedelta(hours=2)
DVOL_POST = pd.Timedelta(hours=24)


def dvol_change(ccy: str, t: pd.Timestamp, dv: dict[str, pd.Series]) -> float | None:
    s = dv[ccy]
    a = s.asof(t - DVOL_PRE)
    b = s.asof(t + DVOL_POST)
    if pd.isna(a) or pd.isna(b) or t - DVOL_PRE < s.index[0]:
        return None
    return float(b - a)


def main() -> None:
    deliv = {"BTC": delivery_prices("btc_usd"), "ETH": delivery_prices("eth_usd")}
    dv = {}
    for c in ("BTC", "ETH"):
        d = pd.read_parquet(CACHE / f"dvol_{c}_1h.parquet")
        dv[c] = pd.Series(
            d["close"].to_numpy(), index=pd.to_datetime(d["ts"], unit="ms", utc=True)
        ).sort_index()
    rows = []
    for name, ccy, t0 in CATALYSTS:
        t = pd.Timestamp(t0, tz="UTC")
        out: dict[str, object] = {"event": name, "ccy": ccy, "release": t}
        ev, why = straddle(ccy, t - CATALYST_LEAD, deliv[ccy], after=t + EXPIRY_BUFFER)
        out["ev_reason"] = why
        cts, dvc = [], []
        for w in CONTROL_WEEKS_A:
            tc = t - pd.Timedelta(weeks=w)
            # control expiry: the same offset from its clock time as the event expiry
            if ev is not None:
                ce = ev["expiry"] - pd.Timedelta(weeks=w)
                c, _ = straddle(ccy, tc - CATALYST_LEAD, deliv[ccy], expiry=ce)
                if c is not None:
                    cts.append(c)
            dvc.append(dvol_change(ccy, tc, dv))
        out["dvol_event"] = dvol_change(ccy, t, dv)
        ok = [x for x in dvc if x is not None]
        out["dvol_control"] = float(np.mean(ok)) if ok else None
        if ev is not None:
            out.update({f"ev_{k}": v for k, v in ev.items()})
        if cts:
            out["ct_ret_notional"] = float(np.mean([c["ret_notional"] for c in cts]))
            out["ct_implied_var"] = float(np.mean([c["implied_var"] for c in cts]))
            out["ct_realised_var"] = float(np.mean([c["realised_var"] for c in cts]))
            out["ct_n"] = len(cts)
        rows.append(out)
    d = pd.DataFrame(rows)
    d.to_csv(HERE / "pilot_a_events.csv", index=False)
    cols = [
        "event",
        "ev_reason",
        "ev_hours_to_expiry",
        "ev_ret_notional",
        "ct_ret_notional",
        "ev_implied_var",
        "ct_implied_var",
        "ev_realised_var",
        "dvol_event",
        "dvol_control",
    ]
    print(d[[c for c in cols if c in d.columns]].to_string(float_format=lambda v: f"{v:.5f}"))
    trials = []
    p = d.dropna(subset=["ev_ret_notional", "ct_ret_notional"]).copy()
    p["pair"] = p["ev_ret_notional"] - p["ct_ret_notional"]
    p["xs_impl"] = p["ev_implied_var"] - p["ct_implied_var"]
    p["mech"] = p["xs_impl"] - (p["ev_realised_var"] - p["ct_realised_var"])
    dates = pd.to_datetime(p["release"]).to_numpy()
    for lbl, col in [
        ("pair", "pair"),
        ("event", "ev_ret_notional"),
        ("excess_implied_var", "xs_impl"),
        ("mech", "mech"),
    ]:
        pt, lo, hi, n = mean_ci(p[col].to_numpy(), dates)
        print(f"  pilot A {lbl:20s} {pt:+.5f} [{lo:+.5f}, {hi:+.5f}] N={n}")
        if lbl == "pair":
            trials.append((2370, "A catalysts straddle", n, pt, lo, hi))
    q = d.dropna(subset=["dvol_event", "dvol_control"]).copy()
    q["dd"] = q["dvol_event"] - q["dvol_control"]
    pt, lo, hi, n = mean_ci(q["dd"].to_numpy(), pd.to_datetime(q["release"]).to_numpy())
    print(f"  DVOL change event minus control (vol pts) {pt:+.3f} [{lo:+.3f}, {hi:+.3f}] N={n}")
    pt2, lo2, hi2, _ = mean_ci(q["dvol_event"].to_numpy(), pd.to_datetime(q["release"]).to_numpy())
    print(f"  DVOL change at event (vol pts) {pt2:+.3f} [{lo2:+.3f}, {hi2:+.3f}] N={n}")
    trials.append((2371, "A catalysts DVOL change", n, pt, lo, hi))
    f = HERE / "trials.csv"
    new = not f.exists()
    with f.open("a", newline="") as fh:
        w = csv.writer(fh)
        if new:
            w.writerow(
                [
                    "trial",
                    "lane",
                    "pilot",
                    "config",
                    "block",
                    "n",
                    "statistic",
                    "point",
                    "ci_low",
                    "ci_high",
                    "verdict",
                    "note",
                    "scored_utc",
                ]
            )
        now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M")
        for tid, cfg, n, pt, lo, hi in trials:
            stat = (
                "mean paired net return on notional, event minus control, at est. touch"
                if tid == 2370
                else "DVOL 24h change (vol points), event minus control"
            )
            w.writerow(
                [
                    tid,
                    "N10",
                    "A catalysts",
                    cfg,
                    "all (exploratory)",
                    n,
                    stat,
                    round(pt, 6),
                    round(lo, 6),
                    round(hi, 6),
                    "EXPLORATORY",
                    "N<=14 heterogeneous events; cannot set direction",
                    now,
                ]
            )


if __name__ == "__main__":
    main()
