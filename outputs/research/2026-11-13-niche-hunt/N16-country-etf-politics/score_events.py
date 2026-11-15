"""
score_events.py
Event-minus-control short-variance P&L on EWZ around Copom decisions and Brazil elections.

A short 30-day variance position is marked from Cboe's VXEWZ (a model-free, mid-based implied
volatility) across a two-session window around each event, and against matched non-event
windows on the same instrument. The difference is the event surplus: how much more implied
variance exceeded realised variance across the event than across ordinary windows. It is a
gross, mid-based measure. Pre-registration: diagnosis.log, 2026-11-13 19:50 UTC.

Usage
-----
    python outputs/research/2026-11-13-niche-hunt/N16-country-etf-politics/score_events.py \
        --block discovery [--trial 2532]
    python .../score_events.py --block heldout        # refuses unless freeze_heldout.md exists

References
----------
Kelly, B., Pastor, L. and Veronesi, P. (2016). The price of political uncertainty: theory and
    evidence from the option market. Journal of Finance 71(5), 2417-2480.
Dubinsky, A., Johannes, M., Kaeck, A. and Seeger, N. (2019). Option pricing of earnings
    announcement risks. Review of Financial Studies 32(2), 646-687.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))
from earnings_iv_crush.research.protocol import date_clustered_ci  # noqa: E402

HERE = Path(__file__).resolve().parent
RAW = HERE / "raw"


# ── configuration ──


@dataclass(frozen=True)
class Cfg:
    tau_days: int = 30  # VXEWZ is a 30-calendar-day index
    control_radius: int = 40  # sessions either side of the event entry
    min_controls: int = 3  # fewer controls cannot centre the event
    weekly_days: int = 7  # tenor of the straddle the surplus is converted into
    # Break-even per round trip on the weekly ATM straddle, % of premium: 2 x (3.13 half-spread
    # from touch_snapshot.csv + 1.35 commission at USD 0.65 x 2 contracts on a USD 96 straddle).
    breakeven_pct: float = 2 * (3.125 + 1.354)
    discovery_end: str = "2019-12-31"
    heldout_start: str = "2020-01-01"


CFG = Cfg()
ELECTIONS = [
    "2014-10-05", "2014-10-26", "2018-10-07", "2018-10-28",
    "2022-10-02", "2022-10-30", "2026-10-04", "2026-10-25",
]  # fmt: skip


# ── data ──


def load_vol(name: str) -> pd.Series:
    df = pd.read_csv(RAW / f"{name}_History.csv")
    df["DATE"] = pd.to_datetime(df["DATE"], format="%m/%d/%Y")
    s = df.set_index("DATE")["CLOSE"].astype(float)
    if s.isna().any() or (s <= 0).any():
        raise ValueError(f"{name}: non-positive or missing closes")
    return s


def load_px(sym: str) -> pd.DataFrame:
    r = json.loads((RAW / f"{sym}_yahoo.json").read_text())["chart"]["result"][0]
    idx = pd.to_datetime(r["timestamp"], unit="s").normalize()
    q = r["indicators"]["quote"][0]
    df = pd.DataFrame(
        {
            "open": q["open"],
            "close": q["close"],
            "adj": r["indicators"]["adjclose"][0]["adjclose"],
        },
        index=idx,
    ).dropna()
    return df[~df.index.duplicated(keep="last")]


def load_copom() -> pd.Series:
    c = json.loads((RAW / "copom_comunicados.json").read_text())["conteudo"]
    return pd.Series(pd.to_datetime([x["dataReferencia"] for x in c])).sort_values()


def load_fomc() -> pd.Series:
    dates = []
    for y in range(2011, 2016):
        html = (RAW / f"fomc_{y}.htm").read_text(encoding="utf-8", errors="ignore")
        dates += sorted(set(re.findall(rf"monetary({y}\d{{4}})a\.htm", html)))
    early = pd.to_datetime(pd.Series(dates), format="%Y%m%d")
    m = pd.read_csv(ROOT / "data/cache/index_events/macro_releases_2016_2026.csv")
    late = pd.to_datetime(m.loc[m["kind"] == "fomc", "date"])
    return pd.concat([early, late]).drop_duplicates().sort_values().reset_index(drop=True)


# ── window P&L ──


def window_pnl(panel: pd.DataFrame, i0: int, i1: int) -> dict:
    """Short 30-day variance from session i0 close to session i1 close, total variance units."""
    d0, d1 = panel.index[i0], panel.index[i1]
    tau = CFG.tau_days / 365.0
    delta = (d1 - d0).days / 365.0
    v0 = (panel["vx"].iat[i0] / 100) ** 2
    v1 = (panel["vx"].iat[i1] / 100) ** 2
    lr = np.diff(np.log(panel["adj"].to_numpy()[i0 : i1 + 1]))
    rv = float(np.sum(lr**2))
    return {
        "d0": d0,
        "d1": d1,
        "v0": v0,
        "v1": v1,
        "rv": rv,
        "implied_drop": v0 * tau - v1 * (tau - delta),
        "pnl": v0 * tau - v1 * (tau - delta) - rv,
        "ret": float(np.sum(lr)),
    }


def build_panel() -> pd.DataFrame:
    vx = load_vol("VXEWZ").rename("vx")
    px = load_px("EWZ")
    panel = px.join(vx, how="inner")
    print(f"funnel: EWZ sessions {len(px)}, VXEWZ days {len(vx)}, joined {len(panel)}")
    return panel


def event_windows(panel: pd.DataFrame, dates: pd.Series, kind: str) -> list[tuple[int, int]]:
    """Session indices (entry, exit) bracketing each event date."""
    idx = panel.index
    out = []
    for d in dates:
        if kind == "copom":
            if d not in idx:
                continue  # decision day missing from the joined panel (holiday or gap)
            k = idx.get_loc(d)
            i0, i1 = k - 1, k + 1
        else:  # weekend election: last session before, first session after
            i1 = int(idx.searchsorted(d))
            i0 = i1 - 1
        if i0 < 0 or i1 >= len(idx):
            continue
        out.append((i0, i1))
    return out


def blocked_mask(panel: pd.DataFrame, blockers: pd.Series) -> np.ndarray:
    """True for sessions within one session of any blocker date (events or weekends after)."""
    idx = panel.index
    pos = np.unique(np.clip(idx.searchsorted(blockers.to_numpy()), 0, len(idx) - 1))
    m = np.zeros(len(idx), dtype=bool)
    for p in pos:
        m[max(p - 1, 0) : min(p + 2, len(idx))] = True
    return m


def score(trial: int, block: str) -> dict:
    panel = build_panel()
    copom = load_copom()
    copom = copom[copom >= panel.index[0]]
    fomc = load_fomc()
    elec = pd.Series(pd.to_datetime(ELECTIONS))
    blockers = pd.concat([copom, fomc, elec]).sort_values()
    blocked = blocked_mask(panel, blockers)
    idx = panel.index

    if trial in (2532, 2533):
        wins = event_windows(panel, copom, "copom")
        print(f"funnel: Copom decisions in panel range {len(copom)}, with windows {len(wins)}")
        fomc_set = set(fomc)
        has_fomc = [any(d in fomc_set for d in idx[i0 : i1 + 1]) for i0, i1 in wins]
        keep = [w for w, f in zip(wins, has_fomc) if f == (trial == 2533)]
        print(f"funnel: {'with' if trial == 2533 else 'without'} FOMC in window {len(keep)}")
        wins = keep
    elif trial == 2534:
        wins = event_windows(panel, elec, "election")
        print(f"funnel: election rounds {len(elec)}, with windows {len(wins)}")
    else:
        raise ValueError(f"unknown trial {trial}")

    lo, hi = (
        (idx[0], pd.Timestamp(CFG.discovery_end))
        if block == "discovery"
        else (pd.Timestamp(CFG.heldout_start), idx[-1])
    )
    wins = [w for w in wins if lo <= idx[w[0]] <= hi]
    print(f"funnel: in {block} block {len(wins)}")

    rows, dropped = [], []
    for i0, i1 in wins:
        ev = window_pnl(panel, i0, i1)
        n_sess, n_cal, wd = i1 - i0, (idx[i1] - idx[i0]).days, idx[i0].weekday()
        ctrl = []
        for j0 in range(max(i0 - CFG.control_radius, 0), min(i0 + CFG.control_radius, len(idx))):
            j1 = j0 + n_sess
            if j1 >= len(idx) or j0 == i0:
                continue
            if idx[j0].weekday() != wd or (idx[j1] - idx[j0]).days != n_cal:
                continue
            if blocked[j0 : j1 + 1].any():
                continue
            ctrl.append(window_pnl(panel, j0, j1)["pnl"])
        if len(ctrl) < CFG.min_controls:
            dropped.append({"d0": idx[i0], "n_ctrl": len(ctrl), "v0": ev["v0"], "ret": ev["ret"]})
            continue
        surplus = ev["pnl"] - float(np.mean(ctrl))
        w_week = ev["v0"] * CFG.weekly_days / 365.0
        rows.append(
            {
                **ev,
                "n_ctrl": len(ctrl),
                "ctrl_pnl": float(np.mean(ctrl)),
                "surplus": surplus,
                "surplus_pct_weekly": 100 * surplus / (2 * w_week),
                "pnl_pct_weekly": 100 * ev["pnl"] / (2 * w_week),
            }
        )
    print(f"funnel: dropped for fewer than {CFG.min_controls} controls {len(dropped)}")
    df = pd.DataFrame(rows)
    if df.empty:
        raise RuntimeError("no scorable events")

    def ci(col: str, scale: float = 1.0) -> dict:
        iv = date_clustered_ci(df[col] * scale, df["d0"], stat=np.mean)
        return {"mean": iv.point, "low": iv.low, "high": iv.high, "n": iv.n}

    out = {
        "trial": trial,
        "block": block,
        "n": len(df),
        "dropped": len(dropped),
        "surplus_var_x1e4": ci("surplus", 1e4),
        "event_pnl_var_x1e4": ci("pnl", 1e4),
        "ctrl_pnl_var_x1e4": ci("ctrl_pnl", 1e4),
        "surplus_pct_weekly": ci("surplus_pct_weekly"),
        "event_pnl_pct_weekly": ci("pnl_pct_weekly"),
        "implied_drop_var_x1e4": ci("implied_drop", 1e4),
        "rv_var_x1e4": ci("rv", 1e4),
        "surplus_sharpe_per_event": float(df["surplus"].mean() / df["surplus"].std(ddof=1)),
        "share_surplus_positive": float((df["surplus"] > 0).mean()),
        "breakeven_pct_weekly_round_trip": CFG.breakeven_pct,
        "cfg": asdict(CFG),
    }
    s = out["surplus_var_x1e4"]
    out["pass"] = bool(
        trial != 2534 and out["surplus_pct_weekly"]["mean"] > CFG.breakeven_pct and s["low"] > 0
    )
    tag = f"{trial}_{block}"
    df.to_csv(HERE / f"events_{tag}.csv", index=False)
    (HERE / f"result_{tag}.json").write_text(json.dumps(out, indent=2, default=str))
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    ap.add_argument("--block", choices=["discovery", "heldout"], required=True)
    ap.add_argument("--trial", type=int, nargs="*", default=[2532, 2533, 2534])
    a = ap.parse_args()
    if a.block == "heldout" and not (HERE / "freeze_heldout.md").exists():
        raise SystemExit("held-out block is locked until freeze_heldout.md exists")
    for t in a.trial:
        print(f"\n=== trial {t} ({a.block}) ===")
        print(json.dumps(score(t, a.block), indent=2, default=str))


if __name__ == "__main__":
    main()
