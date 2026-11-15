"""
decompose_selection.py
Lane L4, exploratory and descriptive: which driver carries the frozen champion's selection.
Reads the walk-forward run written once by ``score_heldout.py`` and the corrected panel; fits
nothing and changes no frozen number. Every figure it prints is labelled exploratory, because
both held-out blocks were viewed before this lane and this check was chosen after the read.

1. Linear-predictor contributions: each feature's ``m_k z_ik`` at the posterior the event was
   predicted from (model scale: positive is a larger loss ratio, worse for the seller), with its
   spread across events and its correlation with the decision.
2. Selection within causal half-spread terciles (cut points from strictly earlier events): if
   the selected-minus-unselected gap vanishes inside terciles, the model is the closed spread
   gate in another form.
3. The gap by L1 P&L component, so the mechanism is named.
4. The closed spread gate itself (half-spread below its causal median) on the same events.

Usage
-----
    python outputs/research/2026-11-14-slate-tests/L4-bayes/decompose_selection.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import l4iter  # noqa: E402
import l4lib  # noqa: E402
import score_heldout as sh  # noqa: E402

from earnings_iv_crush import config as C  # noqa: E402
from earnings_iv_crush.research.protocol import date_clustered_ci  # noqa: E402

PCT = C.ONLINE_BAYES.pct_per_unit
BLOCKS = ("2019-24", "2025-26")
RULES = {"P(H>0)>0.5": "m_decide", "E[H]>0": "m_decide_ev"}


def _causal_quantiles(x: np.ndarray, dates: pd.Series, qs: tuple[float, ...]) -> np.ndarray:
    """Quantiles of ``x`` over events with strictly earlier entry dates (NaN before 200)."""
    d = pd.to_datetime(dates).to_numpy()
    out = np.full((x.size, len(qs)), np.nan)
    uniq = np.unique(d)
    seen: list[float] = []
    by = {t: np.flatnonzero(d == t) for t in uniq}
    for t in uniq:
        idx = by[t]
        if len(seen) >= 200:
            out[idx] = np.quantile(np.asarray(seen), qs)
        seen.extend(x[idx].tolist())
    return out


def _iv(c: Any) -> list[float]:
    return [round(c.point, 3), round(c.low, 3), round(c.high, 3)]


def _ci(v: np.ndarray, keys: np.ndarray) -> list[float]:
    c = date_clustered_ci(v, keys, np.mean)
    return [round(c.point, 4), round(c.low, 4), round(c.high, 4), c.n]


def main() -> None:
    run = pd.read_parquet(HERE / "run_H_corr.parquet")
    path = pd.read_csv(HERE / "coef_path_H_corr.csv", parse_dates=["date"])
    d = l4iter.load_all()
    cfg = C.ONLINE_BAYES_L4_MODEL
    D = l4iter.Design(d)
    X = D.X(cfg)
    names = D.coef_names(cfg)
    ent = d["entry_date"].to_numpy()
    k = np.searchsorted(path["date"].to_numpy(), ent, side="right") - 1
    M = np.full((len(d), len(names)), np.nan)
    ok = k >= 0
    M[ok] = path[[f"m_{c}" for c in names]].to_numpy()[k[ok]]
    contrib = M * X
    y = l4lib.target(d, "H_corr", cfg)
    rv = d["residual_value"].to_numpy(float) * PCT
    hs = d["half_spread"].to_numpy(float)
    terc = _causal_quantiles(hs, d["entry_date"], (1 / 3, 2 / 3))
    med = _causal_quantiles(hs, d["entry_date"], (0.5,))[:, 0]
    out: dict[str, Any] = {"label": "EXPLORATORY: chosen after the held-out read; descriptive"}
    for blk in BLOCKS:
        sc = (
            (d["block"] == blk).to_numpy()
            & run["m_scored"].to_numpy(bool)
            & np.isfinite(y)
            & np.isfinite(terc).all(axis=1)
        )
        keys = d["announce_date"].to_numpy()[sc]
        res: dict[str, Any] = {"N": int(sc.sum())}
        lp = contrib[sc].sum(axis=1)
        res["contrib_sd"] = {
            n: round(float(np.std(contrib[sc, j])), 4) for j, n in enumerate(names) if j > 0
        }
        dec = run["m_decide"].to_numpy(bool)[sc]
        res["contrib_corr_with_decision"] = {
            n: round(float(np.corrcoef(contrib[sc, j], dec)[0, 1]), 3)
            for j, n in enumerate(names)
            if j > 0
        }
        res["linear_predictor_sd"] = round(float(np.std(lp)), 4)
        res["name_effect_sd"] = round(float(np.nanstd(run["m_name_effect_at_entry"][sc])), 4)
        t = np.where(hs[sc] <= terc[sc, 0], 0, np.where(hs[sc] <= terc[sc, 1], 1, 2))
        for rule, col in RULES.items():
            sel = run[col].to_numpy(bool)[sc]
            r: dict[str, Any] = {"n_selected": int(sel.sum())}
            for ti, lab in enumerate(("tight", "mid", "wide")):
                m = t == ti
                s, u = sel & m, ~sel & m
                r[f"{lab}_n_sel_unsel"] = [int(s.sum()), int(u.sum())]
                if s.sum() > 20 and u.sum() > 20:
                    hd = sh._diff_ci(y[sc][m], sel[m], keys[m])
                    rd = sh._diff_ci(rv[sc][m], sel[m], keys[m])
                    r[f"{lab}_sel_minus_unsel_H"] = [round(hd.point, 3), round(hd.low, 3),
                                                     round(hd.high, 3)]  # fmt: skip
                    r[f"{lab}_sel_minus_unsel_rv"] = [round(rd.point, 3), round(rd.low, 3),
                                                      round(rd.high, 3)]  # fmt: skip
            comp = {}
            for c in l4lib.COMPONENTS:
                v = d[c].to_numpy(float)[sc] * PCT
                comp[c] = round(float(v[sel].mean() - v[~sel].mean()), 3)
            r["gap_by_component"] = comp
            r["gap_H"] = round(float(y[sc][sel].mean() - y[sc][~sel].mean()), 3)
            out_key = f"{blk} {rule}"
            res[out_key] = r
        gate = hs[sc] < med[sc]
        res["spread_gate_below_causal_median"] = {
            "n_selected": int(gate.sum()),
            "selected_mean_H": _ci(y[sc][gate], keys[gate]),
            "overlap_with_P_rule": round(float((gate & dec).sum() / max(dec.sum(), 1)), 3),
            "sel_minus_unsel_H": _iv(sh._diff_ci(y[sc], gate, keys)),
        }
        out[blk] = res
        print(f"[{blk}] EXPLORATORY decomposition, N {res['N']}")
        print(json.dumps(res, indent=1)[:4000])
    (HERE / "decomposition.json").write_text(json.dumps(out, indent=2) + "\n", encoding="utf-8")
    print("written decomposition.json")


if __name__ == "__main__":
    main()
