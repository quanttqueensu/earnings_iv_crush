"""
a5_revalue.py
A5: re-value trials 1,819 (tight-of-three straddle strike, entry-night delta-matched) and 1,826
(vol-tight IM/2 strangle, vega-matched to H) under the adopted settlement ``HEDGED_NET``.

Usage
-----
    python outputs/research/2026-11-14-slate-tests/L1-corrections/a5_revalue.py build
    python outputs/research/2026-11-14-slate-tests/L1-corrections/a5_revalue.py score

``build`` re-runs lane B's own per-event builders (``laneB-contract-choice/build.py::build_one``
and ``wings.py::wings_one``), imported and never edited, with the two valuation functions they
call swapped in the imported copies:

- the hedged-event-hold study's ``hedged_short_straddle`` is called with ``cfg=HEDGED_NET``;
- the smile-strike study's ``hedged_short_strangle`` is replaced by the package's netted
  ``hedged_hold.hedged_short_strangle``. Every call also values the package function under
  ``HEDGED`` and raises unless it equals the closed study's result to 1e-12 per share.

The netted per-event values are written to ``a5_net/arms.parquet`` and ``a5_net/wings.parquet``
(lane B's column layout, so its scorer reads them unchanged). ``score`` imports lane B's
``score.py`` and evaluates the frozen 1,819 and 1,826 statistics on the stored (unnetted) and
the netted files, checks the unnetted run reproduces the logged figures, and writes
``a5_results.json``, the 1,826 wing-attrition funnel and its outcome-dependence test.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
import time
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from earnings_iv_crush.config import HEDGED, HEDGED_NET  # noqa: E402
from earnings_iv_crush.research import hedged_hold as hh  # noqa: E402
from earnings_iv_crush.research.protocol import date_clustered_ci  # noqa: E402

HERE = Path(__file__).resolve().parent
LANEB = ROOT / "outputs" / "research" / "2026-11-13-alpha-hunt-2" / "laneB-contract-choice"
NET = HERE / "a5_net"
BASE = HERE / "base_corrected.parquet"
N_WORKERS = 6
STRANGLE_TOL = 1e-12  # per share; package HEDGED against the closed study's strangle
K0_TOL = 1e-12  # m0; netted ATM straddle against base_corrected H_net


def _load(name: str, path: Path) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


# ── netted valuation swapped into the imported closed modules ───────────────

_W: dict[str, Any] = {}


def _netted_straddle(orig: Any) -> Any:
    def value(**kw: Any) -> hh.HedgedResult:
        if not kw.get("hedge", True) or "cfg" in kw:
            return orig(**kw)
        return orig(**kw, cfg=HEDGED_NET)

    return value


def _netted_strangle(orig: Any) -> Any:
    def value(**kw: Any) -> dict:
        ref = orig(**kw)
        n = len(kw["closes"])
        if n == 0:  # no hedging close: nothing to net, the closed result stands
            return ref
        args = dict(
            sale_price=kw["sale"],
            sale_mid=kw["sale"],
            call_strike=kw["kc"],
            put_strike=kw["kp"],
            fwd=float(kw["closes"][0]),  # margin field unused; build_g takes its own base
            closes=kw["closes"],
            rets=kw["rets"],
            taus=kw["taus"],
            call_sigmas=np.full(n, kw["sig_c"]),
            put_sigmas=np.full(n, kw["sig_p"]),
            half_spreads=kw["half_spreads"],
            settle_close=kw["settle"],
        )
        old = hh.hedged_short_strangle(**args, cfg=HEDGED)
        if abs(old.net_pnl - ref["net"]) > STRANGLE_TOL:
            raise RuntimeError(f"package strangle {old.net_pnl} != closed {ref['net']}")
        new = hh.hedged_short_strangle(**args, cfg=HEDGED_NET)
        return {
            "net": new.net_pnl,
            "settlement": new.settlement,
            "hedge_pnl": new.hedge_pnl,
            "eq_cost": new.equity_cost,
            "disposal": new.disposal,
            "peak": new.max_hedge_notional,
        }

    return value


def _init() -> None:
    wg = _load("laneb_wings", LANEB / "wings.py")
    bd, sm, st = wg.bd, wg.sm, wg.st
    st.hedged_short_straddle = _netted_straddle(st.hedged_short_straddle)
    sm.hedged_short_strangle = _netted_strangle(sm.hedged_short_strangle)
    _W.update(wg=wg, bd=bd, st=st, crsp=st.load_crsp())
    f = pd.read_parquet(st.FEATURES)
    for c in ("entry_date", "exit_date", "front_expiry"):
        f[c] = pd.to_datetime(f[c])
    _W["fi"] = f.drop_duplicates(["ticker", "entry_date"]).set_index(
        ["ticker", "entry_date"], drop=False
    )
    pd.read_parquet = bd._cached_read  # type: ignore[assignment]  # lane B's per-event cache


def _one(e: pd.Series) -> tuple[dict, dict]:
    bd, wg = _W["bd"], _W["wg"]
    bd._cache.clear()
    a = bd.build_one(e, _W["fi"].loc[(e["ticker"], e["entry_date"])], _W["crsp"])
    bd._cache.clear()
    w = wg.wings_one(e, _W["crsp"])
    return a, w


def _events() -> pd.DataFrame:
    wg = _load("laneb_wings_main", LANEB / "wings.py")
    bd, st = wg.bd, wg.st
    ev = pd.read_parquet(bd.H_EVENTS)
    ev = ev[ev["status"] == "ok"].copy()
    for c in ("entry_date", "exit_date", "expiry"):
        ev[c] = pd.to_datetime(ev[c])
    f = pd.read_parquet(st.FEATURES)[["ticker", "entry_date", "permno"]]
    f["entry_date"] = pd.to_datetime(f["entry_date"])
    return ev.merge(f.drop_duplicates(["ticker", "entry_date"]), on=["ticker", "entry_date"])


def build(limit: int) -> None:
    ev = _events()
    if limit:
        ev = ev.sample(limit, random_state=0)
    print(f"events: {len(ev)}", flush=True)
    rows: list[tuple[dict, dict]] = []
    t0 = time.time()
    with ProcessPoolExecutor(N_WORKERS, initializer=_init) as ex:
        for i, r in enumerate(ex.map(_one, [e for _, e in ev.iterrows()], chunksize=20)):
            rows.append(r)
            if (i + 1) % 1000 == 0:
                print(f"  {i + 1}/{len(ev)}  {time.time() - t0:.0f}s", flush=True)
    a = pd.DataFrame([r[0] for r in rows])
    w = pd.DataFrame([r[1] for r in rows])
    a = ev.merge(a, on=["ticker", "entry_date"], how="left", suffixes=("", "_b"))
    print("arms funnel:", dict(Counter(a["status_b"])))
    print("wings funnel:", dict(Counter(w["wstatus"])))
    # the netted ATM straddle must be base_corrected's H_net
    b = pd.read_parquet(BASE, columns=["ticker", "entry_date", "H_net"])
    b["entry_date"] = pd.to_datetime(b["entry_date"])
    a = a.merge(b, on=["ticker", "entry_date"], how="left", validate="one_to_one")
    gap = (a["k0_usd"] / a["m0"] - a["H_net"]).abs()
    print(f"k0 netted vs base_corrected H_net: n={int(gap.notna().sum())}, max {gap.max():.2e}")
    if not limit and not (gap.max() <= K0_TOL):
        raise RuntimeError("netted ATM straddle does not reproduce H_net")
    a["H_stored"] = a["H"]
    a["H"] = a["k0_usd"] / a["m0"]  # lane B's scorer reads H as the base arm
    a["H_mid"] = a["k0_usd_mid"] / a["m0"]
    NET.mkdir(exist_ok=True)
    sfx = "" if not limit else "_smoke"
    for frame, name in ((a.drop(columns=["H_net"]), "arms"), (w, "wings")):
        tmp = NET / f"{name}{sfx}.parquet.tmp"
        frame.to_parquet(tmp)
        tmp.replace(NET / f"{name}{sfx}.parquet")  # never leave a half-written result
    print(f"wrote {NET} ({time.time() - t0:.0f}s)")


# ── scoring ─────────────────────────────────────────────────────────────────


def _mean(a: np.ndarray) -> float:
    return float(np.mean(a))


def _diff(x: pd.Series, inside: pd.Series, dates: pd.Series) -> list[float]:
    p, lo, hi = hh.top_minus_bottom_ci(x.to_numpy(float), inside, ~inside, dates)
    return [p, lo, hi]


def _attrition(d: pd.DataFrame, w: pd.DataFrame, base: pd.DataFrame) -> dict:
    """Wing-attrition funnel of 1,826 and whether the drops depend on the outcome."""
    e = d.merge(w, on=["ticker", "entry_date"], how="left", suffixes=("", "_w"))
    e = e.merge(base, on=["ticker", "entry_date"], how="left", validate="one_to_one")
    steps = [
        ("wing quoted at IM/2 on both sides", e["wstatus"].ne("no_wing")),
        ("base wings two-sided", e["wstatus"].eq("ok")),
        ("tight wings hedge-valued", e["tw_status"].eq("ok")),
        ("base IM/2 strangle valued", e["g050_status"].eq("ok")),
    ]
    out: dict = {"n_block": int(len(e)), "steps": []}
    keep = pd.Series(True, index=e.index)
    for lab, m in steps:
        before = int(keep.sum())
        keep = keep & m
        out["steps"].append(
            {"step": lab, "kept": int(keep.sum()), "dropped": before - int(keep.sum())}
        )
    out["n_kept"] = int(keep.sum())
    out["reasons_dropped"] = dict(Counter(e.loc[~keep, "wstatus"].fillna("missing")))
    if (~keep).sum() and keep.sum():
        for col in ("H_net", "residual_value"):
            out[f"dropped_minus_kept_{col}"] = _diff(e[col], ~keep, e["exit_date"])
            out[f"mean_{col}_kept"] = float(e.loc[keep, col].mean())
            out[f"mean_{col}_dropped"] = float(e.loc[~keep, col].mean())
        # does the drop rate rise with the realised move? share dropped by move-ratio bin
        mr = (e["abs_move"] / e["im"]).clip(upper=99)
        bins = pd.cut(mr, [0, 0.5, 1, 1.5, 2, np.inf])
        out["drop_share_by_move_ratio"] = {
            str(k): [float((~keep[v.index]).mean()), int(len(v))]
            for k, v in e.groupby(bins, observed=True)
        }
        # the dropped events' implied move: wings fail to list when the move is large
        out["im_median_kept_dropped"] = [
            float(e.loc[keep, "im"].median()),
            float(e.loc[~keep, "im"].median()),
        ]
    return out


def score() -> None:
    sc = _load("laneb_score", LANEB / "score.py")
    blocks = {"disc": (2013, 2018), "held": (2019, 2024)}
    logged = json.loads((LANEB / "results_held_1819_1826.json").read_text(encoding="utf-8"))
    base = pd.read_parquet(BASE, columns=["ticker", "entry_date", "H_net", "residual_value"])
    base["entry_date"] = pd.to_datetime(base["entry_date"])
    res: dict = {}
    for tag, folder in (("stored", LANEB), ("netted", NET)):
        sc.HERE = folder  # load() and vega_matched() read arms/wings from HERE
        d_all = sc.load()
        w = pd.read_parquet(folder / "wings.parquet")
        w["entry_date"] = pd.to_datetime(w["entry_date"])
        for blk, (y0, y1) in blocks.items():
            d = d_all[d_all["year"].between(y0, y1) & d_all["status_b"].eq("ok")]
            for tid in (1819, 1826):
                out = sc.TRIALS_DEF[tid][1](d)
                r = out["res"]
                res[f"{tag}_{tid}_{blk}"] = {
                    "res": [r["point"], r["low"], r["high"], r["n"], r["t"]],
                    "null_pct": out.get("null_pct"),
                    "level_chosen": [out["level_chosen"][k] for k in ("point", "low", "high")],
                    "level_H_same": out["level_H_same"],
                    "funnel": out["funnel"],
                }
                if tid == 1819:
                    res[f"{tag}_{tid}_{blk}"]["decomp_on_switched"] = out["decomp_on_switched"]
                    res[f"{tag}_{tid}_{blk}"]["share_switched"] = out["share_switched"]
            if tag == "netted":
                d2 = d.copy()
                d2["entry_date"] = pd.to_datetime(d2["entry_date"])
                res[f"attrition_1826_{blk}"] = _attrition(d2, w, base)
    for tid in (1819, 1826):
        got, want = res[f"stored_{tid}_held"]["res"][0], logged[str(tid)]["res"]["point"]
        if abs(got - want) > 1e-12:
            raise RuntimeError(f"{tid} stored rerun {got} != logged {want}")
    res["reproduced_logged_held"] = True
    # netting's own effect on the paired statistic, per event: netted minus stored
    sc.HERE = LANEB
    old = sc.load()
    sc.HERE = NET
    new = sc.load()
    k = ["ticker", "entry_date"]
    p = old.merge(new, on=k, suffixes=("_o", "_n"))
    for blk, (y0, y1) in blocks.items():
        q = p[p["year_o"].between(y0, y1) & p["status_b_o"].eq("ok")]
        x = {}
        for lab in ("k0", "km1", "kp1"):
            dd = (q[f"{lab}_usd_n"] - q[f"{lab}_usd_o"]) / q["m0_o"]
            iv = date_clustered_ci(
                dd.dropna().to_numpy(float), q.loc[dd.notna(), "exit_date_o"], _mean
            )
            x[f"netting_{lab}"] = [iv.point, iv.low, iv.high, iv.n]
        res[f"netting_by_strike_{blk}"] = x
    (HERE / "a5_results.json").write_text(json.dumps(res, indent=1, default=str), encoding="utf-8")
    print(json.dumps(res, indent=1, default=str))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", choices=["build", "score"])
    ap.add_argument("--limit", type=int, default=0)
    a = ap.parse_args()
    if a.mode == "build":
        build(a.limit)
    else:
        score()


if __name__ == "__main__":
    main()
