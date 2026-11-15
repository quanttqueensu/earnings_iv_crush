"""stage_a_adjusted.py: trial 2478, trial 2472 on market-adjusted returns (r - beta x r_SPY).

Same nights, controls, windows and exclusions as stage_a_moves.py; beta and the residual
standard deviation come from the same 60-session window. Pre-registered in diagnosis.log entry 2.

Usage
-----
    python outputs/research/2026-11-13-niche-hunt/N14-bank-stress-tests-and-regulatory/stage_a_adjusted.py
"""
from __future__ import annotations

import os

import numpy as np
import pandas as pd

from stage_a_moves import (CONTROL_LAGS, EARN_EXCL, EXCLUDED_NIGHTS, HERE, PRIMARY, SIG_GAP,
                           SIG_WIN, date_clustered_ci, load, mean)


def main() -> None:
    px, earn, macro = load()
    cal = pd.read_csv(os.path.join(HERE, "stress_calendar.csv"))
    cal["night"] = pd.to_datetime(cal["night"])
    cal = cal[(cal["night"] >= "2015-01-01") & ~cal["night"].isin(EXCLUDED_NIGHTS)]
    sessions = px.index
    pos = {d: i for i, d in enumerate(sessions)}
    first = cal.groupby("cycle")["night"].min().to_dict()
    ev_idx = {pos[n] for n in cal["night"]}
    m = px["SPY"].pct_change()
    rows = []
    for t in PRIMARY:
        r = px[t].pct_change()
        e_idx = set()
        for d in earn.get(t, []):
            i = sessions.searchsorted(d)
            e_idx.update(range(i - EARN_EXCL, i + EARN_EXCL + 1))
        for _, ev in cal.iterrows():
            i, fi = pos[ev["night"]], pos[first[ev["cycle"]]]
            win = [k for k in range(fi - SIG_GAP - SIG_WIN, fi - SIG_GAP) if k not in e_idx]
            y, x = r.iloc[win].to_numpy(), m.iloc[win].to_numpy()
            beta = np.cov(y, x)[0, 1] / np.var(x, ddof=1)
            s = np.std(y - beta * x, ddof=1)
            ab = lambda k: (r.iloc[k] - beta * m.iloc[k]) / s  # noqa: E731
            ctrl = [ab(i - lag + 1) ** 2 for lag in CONTROL_LAGS
                    if not any(abs(i - lag - j) <= 3 for j in ev_idx)
                    and (i - lag) not in e_idx and (i - lag + 1) not in e_idx
                    and sessions[i - lag + 1] not in macro]
            if not ctrl:
                continue
            rows.append({"ticker": t, "night": ev["night"], "night_type": ev["night_type"],
                         "z2": ab(i + 1) ** 2, "z2_ctrl": np.mean(ctrl), "beta": beta})
    d = pd.DataFrame(rows)
    d["excess"] = d["z2"] - d["z2_ctrl"]
    d.to_csv(os.path.join(HERE, "stage_a_adjusted_rows.csv"), index=False)
    for blk, sel in [("discovery 2015-19", d["night"] < "2020-01-01"),
                     ("held-out 2020-26", d["night"] >= "2020-01-01")]:
        x = d[sel]
        ci = date_clustered_ci(x["excess"], x["night"], stat=mean)
        print(f"2478 market-adjusted, {blk}: excess {ci.point:+.3f} [{ci.low:+.3f}, "
              f"{ci.high:+.3f}] N={ci.n} nights={ci.clusters}; event z2 {x['z2'].mean():.2f}, "
              f"control z2 {x['z2_ctrl'].mean():.2f}, median beta {x['beta'].median():.2f}")


if __name__ == "__main__":
    main()
