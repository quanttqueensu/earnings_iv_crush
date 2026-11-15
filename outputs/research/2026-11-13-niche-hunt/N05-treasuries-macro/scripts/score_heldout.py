"""score_heldout.py: the single read of the 2021-2026 held-out block (trials 2212-2215).

Frozen by ``freeze_N05_vxtlt.md``. Refuses to run if ``vx_lib.py`` has changed since the freeze,
or if the held-out result file already exists (the block is read once).

Usage:
    python outputs/research/2026-11-13-niche-hunt/N05-treasuries-macro/scripts/score_heldout.py

Pass rules (co-primary, Bonferroni over two tests, so 97.5% intervals):
    2212 FOMC, short 30-day straddle one-day return, event minus controls: mean > 0 and the
         97.5% lower bound > 0.
    2213 pooled NFP, CPI and FOMC, same metric and rule.
Secondary, no pass rule: 2214 pooled and 2215 FOMC on the variance metric of H1.
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import numpy as np

from vx_lib import CFG, LANE, build_events, load_panel
from earnings_iv_crush.research.protocol import date_clustered_ci

LIB_SHA256 = "030df0c162c7737259fe7cc3559aaca8720dcabd8b727ee2a2c3a039d07b1095"
OUT = LANE / "logs" / "heldout_results.json"
CI_PRIMARY = 0.975


def _check() -> None:
    lib = Path(__file__).with_name("vx_lib.py").read_bytes()
    got = hashlib.sha256(lib).hexdigest()
    if got != LIB_SHA256:
        sys.exit(f"vx_lib.py changed since the freeze: {got} != {LIB_SHA256}")
    if OUT.exists():
        sys.exit(f"{OUT} exists: the held-out block has already been read")


def _score(df, label: str, ci: float, rule: bool) -> dict:
    iv = date_clustered_ci(df["d"], df["month"], stat=np.mean, n_boot=CFG.n_boot, seed=CFG.seed, ci=ci)
    sd = float(df["d"].std(ddof=1))
    res = {
        "label": label,
        "ci": ci,
        "n": iv.n,
        "clusters": iv.clusters,
        "mean": iv.point,
        "lo": iv.low,
        "hi": iv.high,
        "sharpe": float(df["d"].mean() / sd),
        "event_mean": float(df["event"].mean()),
        "control_mean": float(df["control"].mean()),
        "median_d": float(df["d"].median()),
        "share_pos": float((df["d"] > 0).mean()),
    }
    if rule:
        res["pass"] = bool(res["mean"] > 0 and res["lo"] > 0)
    print(json.dumps(res))
    return res


if __name__ == "__main__":
    _check()
    panel = load_panel()
    s, e = CFG.held_start, CFG.held_end
    st = build_events(panel, s, e, "straddle")
    fomc = st[st["kinds"].str.contains("fomc")]
    out = {
        "2212_fomc_straddle": _score(fomc, "2212 FOMC straddle (held-out)", CI_PRIMARY, True),
        "2213_pooled_straddle": _score(st, "2213 pooled straddle (held-out)", CI_PRIMARY, True),
    }
    for k in ("nfp", "cpi"):
        out[f"type_{k}_straddle"] = _score(st[st["kinds"].str.contains(k)], f"{k} straddle (held-out, descriptive)", 0.95, False)
    var = build_events(panel, s, e, "y")
    out["2214_pooled_variance"] = _score(var, "2214 pooled variance metric (held-out)", 0.95, False)
    out["2215_fomc_variance"] = _score(var[var["kinds"].str.contains("fomc")], "2215 FOMC variance metric (held-out)", 0.95, False)
    st.to_csv(LANE / "logs" / "heldout_events_straddle.csv", index=False)
    OUT.write_text(json.dumps(out, indent=2, default=str))
