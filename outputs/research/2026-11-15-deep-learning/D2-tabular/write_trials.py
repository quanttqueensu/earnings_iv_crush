"""
write_trials.py
Lane D2: writes trials.csv from the frozen held-out outputs on disk (heldout_2019-24.json and,
when present, heldout_2025-26.json). Fits nothing; every number is copied from those files.

Usage
-----
    python outputs/research/2026-11-15-deep-learning/D2-tabular/write_trials.py
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parent
FIRST = {"2019-24": 3182, "2025-26": 3186}


def _iv(lo: float, hi: float) -> str:
    return f"[{lo:+.4f}, {hi:+.4f}]"


def rows_for(block: str) -> list[dict[str, object]]:
    path = HERE / f"heldout_{block}.json"
    if not path.exists():
        return []
    r = json.loads(path.read_text(encoding="utf-8"))
    f, e = r["forecaster"], r["economics"]
    tid = FIRST[block]
    tag = " (exploratory)" if block == "2025-26" else ""
    g, t = f["gm_minus_l4_model"], f["t_minus_l4_model"]
    yp = f"{f['years_positive_gm']} of {f['n_years']} years positive"
    out: list[dict[str, object]] = [
        {
            "trial_id": tid,
            "idea": "D2 tabular MDN, Gaussian head c17, 5-seed ensemble, quarterly refits",
            "rule": "D2 minus L4 champion log score of H_net (% of m0), nats per event",
            "block": block,
            "N": g["N"],
            "statistic": f"{g['mean']:+.5f}",
            "interval": _iv(*g["ci"]),
            "verdict": (
                ("pass" if g["ci"][0] > 0 and f["years_positive_gm"] >= 4 else "fail")
                if block == "2019-24"
                else ("interval above zero" if g["ci"][0] > 0 else "interval includes zero")
            )
            + f"{tag}; {yp}",
        },
        {
            "trial_id": tid + 1,
            "idea": "D2 tabular MDN, Student-t head c14 (log score only), 5-seed ensemble",
            "rule": "D2-t minus L4 champion log score of H_net (% of m0), nats per event",
            "block": block,
            "N": t["N"],
            "statistic": f"{t['mean']:+.5f}",
            "interval": _iv(*t["ci"]),
            "verdict": ("pass" if t["ci"][0] > 0 else "fail") + tag,
        },
    ]
    for name, off in (("H_net", 2), ("residual_value", 3)):
        b = e[name]
        smt = b.get("sel_minus_tight", [float("nan")] * 3)
        out.append(
            {
                "trial_id": tid + off,
                "idea": f"D2 economic rule on {name} (% of m0 per trade, net at the touch)",
                "rule": "trade if quadrature E[H_net] > 0; selected minus tight-spread-per-date "
                "screen; matched-null percentile",
                "block": block,
                "N": b["n_selected"],
                "statistic": f"sel-tight {smt[0]:+.4f}; null pct {b.get('null_percentile')}",
                "interval": _iv(smt[1], smt[2]),
                "verdict": ("pass" if b.get("economic_pass") else "fail") + tag,
            }
        )
    return out


def main() -> None:
    rows = rows_for("2019-24") + rows_for("2025-26")
    pd.DataFrame(rows).to_csv(HERE / "trials.csv", index=False)
    print(pd.DataFrame(rows).to_string(index=False))


if __name__ == "__main__":
    main()
