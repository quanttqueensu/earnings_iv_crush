"""f3_risk.py: F3, a same-session concentration cap on the hedged hold, as a risk read.

Caps of 3, 5 and 10 events per entry session, events kept uniformly at random (seeded draws), on
base_corrected H_corr with one unit of m0 per event. Reports trades, per-trade mean, worst-session
loss, maximum drawdown, session sd and tail share against the uncapped book, by block. Not a
trial: nothing is selected on an outcome or a feature.

Usage
-----
    python outputs/research/2026-11-14-slate-tests/L3-selection/f3_risk.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import lib  # noqa: E402

from earnings_iv_crush.research.protocol import date_clustered_ci  # noqa: E402

CAPS = (None, 10, 5, 3)
N_DRAWS = 200  # random keep-sets per cap; enough for stable 5-95% bands on the risk figures
TAIL_Q = 0.05  # worst 5% of sessions
SEED = 0
SIZE_EDGES = [0, 3, 5, 10, 20, 1000]  # events per session, for the sd-by-count table


def book_stats(h: np.ndarray, sess: np.ndarray) -> dict[str, float]:
    """Risk figures of a book in units of one event's m0 (h in % of m0)."""
    s = pd.Series(h).groupby(sess).sum().sort_index()
    cum = s.cumsum().to_numpy()
    peak = np.maximum.accumulate(np.concatenate([[0.0], cum]))[1:]
    dd = float(np.max(peak - cum))
    loss = s[s < 0]
    k = max(1, int(np.ceil(TAIL_Q * len(s))))
    tail = float(s.nsmallest(k).sum() / loss.sum()) if len(loss) else float("nan")
    return {
        "trades": float(h.size),
        "mean": float(h.mean()),
        "total": float(s.sum()),
        "worst_session": float(s.min()),
        "max_dd": dd,
        "max_dd_per_1000_trades": 1000 * dd / h.size,
        "session_sd": float(s.std(ddof=1)),
        "tail_share": tail,
        "sessions": float(len(s)),
    }


def main() -> None:
    b = lib.load_base()
    b["block"] = lib.block_of(b["year"])
    b = b[b["H_corr"].notna()].sort_values("entry_date").reset_index(drop=True)
    rng = np.random.default_rng(SEED)
    out: dict = {}
    for name, _, _ in lib.CFG.blocks:
        g = b[b["block"] == name].reset_index(drop=True)
        sess = g["entry_date"].dt.normalize().to_numpy()
        h = 100 * g["H_corr"].to_numpy(float)
        counts = g.groupby("entry_date").size()
        res: dict = {
            "N": int(len(g)),
            "sessions": int(counts.size),
            "events_per_session_p50_p90_max": [
                float(counts.median()),
                float(counts.quantile(0.9)),
                float(counts.max()),
            ],
            "share_events_in_sessions_over_10": float(counts[counts > 10].sum() / counts.sum()),
        }
        for cap in CAPS:
            if cap is None:
                st = book_stats(h, sess)
                ci = date_clustered_ci(h, g["exit_date"], np.mean)
                st.update(mean_lo=ci.low, mean_hi=ci.high)
                res["uncapped"] = st
                continue
            draws = []
            for _ in range(N_DRAWS):
                rank = pd.Series(rng.random(len(g))).groupby(sess).rank(method="first")
                keep = rank.to_numpy() <= cap
                draws.append(book_stats(h[keep], sess[keep]))
            dfx = pd.DataFrame(draws)
            res[f"cap{cap}"] = {
                c: {
                    "median": float(dfx[c].median()),
                    "p05": float(dfx[c].quantile(0.05)),
                    "p95": float(dfx[c].quantile(0.95)),
                }
                for c in dfx.columns
            }
        s = pd.DataFrame({"h": h, "sess": sess}).groupby("sess")["h"].agg(["sum", "size"])
        lab = pd.cut(s["size"], SIZE_EDGES).astype(str)
        res["session_sd_by_count"] = {k: float(v) for k, v in s.groupby(lab)["sum"].std().items()}
        res["per_event_mean_by_session_size"] = {
            k: float(v) for k, v in (s["sum"] / s["size"]).groupby(lab).mean().items()
        }
        res["sessions_by_size"] = {k: int(v) for k, v in lab.value_counts().items()}
        out[name] = res
        print(
            name,
            {
                k: res[k]
                for k in (
                    "N",
                    "sessions",
                    "events_per_session_p50_p90_max",
                    "share_events_in_sessions_over_10",
                )
            },
        )
        u = res["uncapped"]
        print(
            f"  uncapped: trades {u['trades']:.0f} mean {u['mean']:+.3f} [{u['mean_lo']:+.3f}, "
            f"{u['mean_hi']:+.3f}] worst {u['worst_session']:+.1f} maxDD {u['max_dd']:.1f} "
            f"DD/1000tr {u['max_dd_per_1000_trades']:.1f} sd {u['session_sd']:.2f} "
            f"tail {u['tail_share']:.3f}"
        )
        for cap in CAPS[1:]:
            r = res[f"cap{cap}"]
            f = {k: v["median"] for k, v in r.items()}
            print(
                f"  cap{cap}: trades {f['trades']:.0f} mean {f['mean']:+.3f} "
                f"[{r['mean']['p05']:+.3f}, {r['mean']['p95']:+.3f}] worst "
                f"{f['worst_session']:+.1f} [{r['worst_session']['p05']:+.1f}, "
                f"{r['worst_session']['p95']:+.1f}] maxDD {f['max_dd']:.1f} DD/1000tr "
                f"{f['max_dd_per_1000_trades']:.1f} sd {f['session_sd']:.2f} "
                f"tail {f['tail_share']:.3f}"
            )
        print(
            "  session sd by count:",
            {k: round(v, 2) for k, v in res["session_sd_by_count"].items()},
        )
        print(
            "  per-event mean by session size:",
            {k: round(v, 3) for k, v in res["per_event_mean_by_session_size"].items()},
            res["sessions_by_size"],
        )
    (HERE / "f3_risk.json").write_text(json.dumps(out, indent=2), encoding="utf-8")
    for name, _, _ in lib.CFG.blocks:
        lib.log_view(
            name, "hedged_hold", "session_concentration_cap", "L3 f3_risk.py", "descriptive"
        )


if __name__ == "__main__":
    main()
