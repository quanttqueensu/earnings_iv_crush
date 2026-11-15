"""
score_elections_eu.py
Trial 2535: event-minus-control short-variance P&L on the Euro Stoxx 50 around European
national elections and referendums, marked from VSTOXX (STOXX free history, model-free,
mid-based). Pre-registration: diagnosis.log, amendment 1 (2026-11-13 20:10 UTC).

Usage
-----
    python outputs/research/2026-11-13-niche-hunt/N16-country-etf-politics/score_elections_eu.py \
        --block discovery
    python .../score_elections_eu.py --block heldout   # refuses unless freeze_heldout.md exists

References
----------
Kelly, B., Pastor, L. and Veronesi, P. (2016). The price of political uncertainty: theory and
    evidence from the option market. Journal of Finance 71(5), 2417-2480.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

from score_events import CFG, ROOT, date_clustered_ci, load_fomc, window_pnl  # noqa: F401

HERE = Path(__file__).resolve().parent
RAW = HERE / "raw"
TRIAL = 2535
BREXIT_ENTRY = pd.Timestamp("2016-06-23")

# (entry close, exit close) in Euro Stoxx 50 sessions; Sunday votes use Friday and Monday.
_SUNDAY = [
    "2013-09-22", "2014-05-25", "2015-01-25", "2015-07-05", "2015-09-20", "2015-12-20",
    "2016-12-04", "2017-04-23", "2017-05-07", "2017-06-18", "2017-09-24", "2018-03-04",
    "2019-04-28", "2019-05-26", "2019-07-07", "2019-11-10",
    "2021-09-26", "2022-04-10", "2022-04-24", "2022-06-12", "2022-06-19", "2022-09-25",
    "2023-05-21", "2023-06-25", "2023-07-23", "2024-06-09", "2024-06-30", "2025-02-23",
]  # fmt: skip
_EXPLICIT = [
    ("2013-02-22", "2013-02-26"),  # Italy, polls closed Monday afternoon
    ("2015-05-07", "2015-05-08"),  # UK, Thursday vote, overnight count
    ("2016-06-23", "2016-06-27"),  # UK EU referendum merged with Spain 2016-06-26
    ("2017-03-15", "2017-03-16"),  # Netherlands, Wednesday vote
    ("2017-06-08", "2017-06-12"),  # UK 2017 merged with France legislative R1
    ("2019-12-12", "2019-12-13"),  # UK
    ("2021-03-17", "2021-03-18"),  # Netherlands
    ("2023-11-22", "2023-11-23"),  # Netherlands
    ("2024-07-04", "2024-07-08"),  # UK 2024 merged with France legislative R2
    ("2025-10-29", "2025-10-30"),  # Netherlands
]  # fmt: skip


def build_panel() -> pd.DataFrame:
    v = pd.read_csv(RAW / "h_v2tx.txt", sep=";")
    v["Date"] = pd.to_datetime(v["Date"], format="%d.%m.%Y")
    vx = v.set_index("Date")["Indexvalue"].astype(float).rename("vx")
    r = json.loads((RAW / "STOXX50E_yahoo.json").read_text())["chart"]["result"][0]
    px = pd.Series(
        r["indicators"]["quote"][0]["close"],
        index=pd.to_datetime(r["timestamp"], unit="s").normalize(),
        name="adj",
    ).dropna()
    px = px[~px.index.duplicated(keep="last")]
    panel = pd.concat([px, vx], axis=1, join="inner")
    panel = panel[panel.index >= "2011-01-01"]
    if (panel["vx"] <= 0).any():
        raise ValueError("non-positive VSTOXX")
    print(f"funnel: SX5E closes {len(px)}, VSTOXX days {len(vx)}, joined since 2011 {len(panel)}")
    return panel


def event_windows(panel: pd.DataFrame) -> list[tuple[int, int]]:
    idx = panel.index
    wins = []
    for d in pd.to_datetime(_SUNDAY):
        i1 = int(idx.searchsorted(d))
        wins.append((i1 - 1, i1))
    for e0, e1 in _EXPLICIT:
        a, b = pd.Timestamp(e0), pd.Timestamp(e1)
        if a not in idx or b not in idx:
            raise RuntimeError(f"explicit window {e0}..{e1} not on the joined calendar")
        wins.append((idx.get_loc(a), idx.get_loc(b)))
    wins.sort()
    for (_, a1), (b0, _) in zip(wins, wins[1:]):
        if b0 <= a1:  # windows sharing a session must have been merged by hand
            raise RuntimeError(f"overlapping windows {idx[a0].date()} and {idx[b0].date()}")
    return wins


def score(block: str) -> dict:
    panel = build_panel()
    idx = panel.index
    wins = event_windows(panel)
    print(f"funnel: event windows {len(wins)}")
    blockers = sorted({idx[k] for i0, i1 in wins for k in range(i0, i1 + 1)} | set(load_fomc()))
    pos = np.unique(np.clip(idx.searchsorted(pd.DatetimeIndex(blockers)), 0, len(idx) - 1))
    blocked = np.zeros(len(idx), dtype=bool)
    for p in pos:
        blocked[max(p - 1, 0) : min(p + 2, len(idx))] = True

    lo, hi = (
        (pd.Timestamp("2013-01-01"), pd.Timestamp(CFG.discovery_end))
        if block == "discovery"
        else (pd.Timestamp(CFG.heldout_start), idx[-1])
    )
    wins = [w for w in wins if lo <= idx[w[0]] <= hi]
    print(f"funnel: in {block} block {len(wins)}")

    rows, dropped = [], 0
    for i0, i1 in wins:
        ev = window_pnl(panel, i0, i1)
        n_sess, n_cal, wd = i1 - i0, (idx[i1] - idx[i0]).days, idx[i0].weekday()
        ctrl = []
        for j0 in range(max(i0 - CFG.control_radius, 0), min(i0 + CFG.control_radius, len(idx))):
            j1 = j0 + n_sess
            if j1 >= len(idx) or idx[j0].weekday() != wd or (idx[j1] - idx[j0]).days != n_cal:
                continue
            if blocked[j0 : j1 + 1].any():
                continue
            ctrl.append(window_pnl(panel, j0, j1)["pnl"])
        if len(ctrl) < CFG.min_controls:
            dropped += 1
            print(f"  dropped {idx[i0].date()}: {len(ctrl)} controls")
            continue
        w_week = ev["v0"] * CFG.weekly_days / 365.0
        surplus = ev["pnl"] - float(np.mean(ctrl))
        rows.append(
            {
                **ev,
                "n_ctrl": len(ctrl),
                "ctrl_pnl": float(np.mean(ctrl)),
                "surplus": surplus,
                "surplus_pct_weekly": 100 * surplus / (2 * w_week),
            }
        )
    df = pd.DataFrame(rows)
    print(f"funnel: dropped for fewer than {CFG.min_controls} controls {dropped}; scored {len(df)}")
    if df.empty:
        raise RuntimeError("no scorable events")

    def ci(frame: pd.DataFrame, col: str, scale: float = 1.0) -> dict:
        iv = date_clustered_ci(frame[col] * scale, frame["d0"], stat=np.mean)
        return {"mean": iv.point, "low": iv.low, "high": iv.high, "n": iv.n}

    no_brexit = df[df["d0"] != BREXIT_ENTRY]
    out = {
        "trial": TRIAL,
        "block": block,
        "n": len(df),
        "dropped": dropped,
        "surplus_var_x1e4": ci(df, "surplus", 1e4),
        "event_pnl_var_x1e4": ci(df, "pnl", 1e4),
        "ctrl_pnl_var_x1e4": ci(df, "ctrl_pnl", 1e4),
        "implied_drop_var_x1e4": ci(df, "implied_drop", 1e4),
        "rv_var_x1e4": ci(df, "rv", 1e4),
        "surplus_pct_weekly": ci(df, "surplus_pct_weekly"),
        "surplus_sharpe_per_event": float(df["surplus"].mean() / df["surplus"].std(ddof=1)),
        "share_surplus_positive": float((df["surplus"] > 0).mean()),
        "sensitivity_ex_brexit_surplus_var_x1e4": (
            ci(no_brexit, "surplus", 1e4) if len(no_brexit) < len(df) else None
        ),
    }
    s = out["surplus_var_x1e4"]
    out["pass"] = bool(s["mean"] > 0 and s["low"] > 0)
    tag = f"{TRIAL}_{block}"
    df.to_csv(HERE / f"events_{tag}.csv", index=False)
    (HERE / f"result_{tag}.json").write_text(json.dumps(out, indent=2, default=str))
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    ap.add_argument("--block", choices=["discovery", "heldout"], required=True)
    a = ap.parse_args()
    if a.block == "heldout" and not (HERE / "freeze_heldout.md").exists():
        raise SystemExit("held-out block is locked until freeze_heldout.md exists")
    print(json.dumps(score(a.block), indent=2, default=str))


if __name__ == "__main__":
    main()
