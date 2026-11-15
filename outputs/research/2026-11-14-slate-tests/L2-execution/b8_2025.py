"""
b8_2025.py
L2 idea B8, exploratory 2025-26 read: the frozen B8 rule (``b8_strangle.py``, imported unchanged)
on the 2025-26 events whose Yahoo stock path L1 rebuilt. Read after the 2019-24 held-out read;
block_is_clean is False for hedged_event_hold 2025-26, so this is exploratory only.

Usage
-----
    python outputs/research/2026-11-14-slate-tests/L2-execution/b8_2025.py
"""

from __future__ import annotations

import os
import sys
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import pandas as pd  # noqa: E402

import b8_strangle as B  # noqa: E402
import l2lib as L  # noqa: E402


def main() -> None:
    d = L.load_base()
    d = d[(d["block"] == "2025-26") & (d["h_status"] == "ok")]
    f = pd.read_parquet(B.FC)
    f["entry_date"] = pd.to_datetime(f["entry_date"])
    m = d[["ticker", "entry_date", "expiry", "m0", "year", "exit_date", "H_net"]].merge(
        f, on=["ticker", "entry_date"], how="left", validate="one_to_one"
    )
    miss = m["yhat_m1"].isna() | m["yhat_m0"].isna()
    print(f"events 2025-26 rebuilt {len(m)}; no out-of-sample M1 forecast {int(miss.sum())}")
    jobs = [dict(r) for _, r in m[~miss].iterrows()]
    workers = max(1, (os.cpu_count() or 2) - 4)
    with ProcessPoolExecutor(max_workers=workers, initializer=B._init) as ex:
        res = list(ex.map(B._one, jobs, chunksize=20))
    b = pd.DataFrame(res).merge(
        m[["ticker", "entry_date", "m0", "exit_date", "H_net"]], on=["ticker", "entry_date"]
    )
    funnel = dict(Counter(b["b8_status"]).most_common())
    print("funnel:", funnel)
    ok = b[b["b8_status"] == "ok"].reset_index(drop=True)
    gap = (ok["straddle_net"] / ok["m0"] - ok["H_net"]).abs().max()
    if gap > 1e-9:
        raise AssertionError(f"straddle on recorded path misses H_net by {gap:.2e}")
    m0, dates = ok["m0"], ok["exit_date"]
    s0, s1 = ok["s0_net"] / m0, ok["s1_net"] / m0
    res2 = {
        "block": "2025-26",
        "funnel": funnel,
        "n": len(ok),
        "primary_forecast_minus_im2": L.iv_dict(L.mean_ci(s1 - s0, dates)),
        "forecast_minus_straddle": L.iv_dict(L.mean_ci(s1 - ok["H_net"], dates)),
        "im2_minus_straddle": L.iv_dict(L.mean_ci(s0 - ok["H_net"], dates)),
        "width_ratio_median": float((ok["w1"] / ok["w0"]).median()),
        "decomposition_forecast_minus_im2": {
            c: float(
                ((ok[f"s1_{c}"] - ok[f"s0_{c}"]) / m0).mean()
                * 100
                * (1 if c in ("premium", "hedge") else -1)
            )
            for c in ("premium", "settlement", "hedge", "equity_cost")
        },
    }
    for k, v in res2.items():
        print(k, v)
    L.write_json(L.HERE / "b8_2025-26.json", res2)
    L.record_view(
        "2025-26", "execution_strangle_width_forecast", "L2-execution b8_2025.py", "descriptive"
    )


if __name__ == "__main__":
    main()
