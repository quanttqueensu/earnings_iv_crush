"""
build_paths.py
L2 execution: record, for every hedged event of ``base_corrected.parquet``, the exact inputs of
its ``H_corr`` valuation (netted, early call assignment with the rate term, financing), so the
execution levers can re-value the same path with one input changed.

Usage
-----
    python outputs/research/2026-11-14-slate-tests/L2-execution/build_paths.py
    python outputs/research/2026-11-14-slate-tests/L2-execution/build_paths.py --limit 50

L1's ``build_base.py`` is imported, never edited. Its module-level ``hh`` is replaced, in the
imported copy only, by a proxy whose ``hedged_short_straddle`` keeps the keyword arguments of the
last call per event; in ``build_one`` that call is the ``H_corr`` valuation (``r_np``). The
recorded inputs are re-valued and must reproduce the stored ``H_corr`` to 1e-12 of m0 or the
script raises. Output: ``_cache/paths.pkl`` (written to a temporary name, then renamed).
"""

from __future__ import annotations

import argparse
import importlib.util
import os
import pickle
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from earnings_iv_crush.research import hedged_hold as hh_real  # noqa: E402

HERE = Path(__file__).resolve().parent
L1 = HERE.parent / "L1-corrections"
BASE_CORR = L1 / "base_corrected.parquet"
OUT = HERE / "_cache" / "paths.pkl"
TOL = 1e-12  # m0; the recorded inputs must give back the stored H_corr this closely


class _HHProxy:
    """Stands in for ``hedged_hold`` inside the imported ``build_base``; records the last call."""

    def __init__(self) -> None:
        self.last: dict | None = None

    def __getattr__(self, name: str) -> Any:
        return getattr(hh_real, name)

    def hedged_short_straddle(self, **kw: Any) -> hh_real.HedgedResult:
        self.last = dict(kw)
        return hh_real.hedged_short_straddle(**kw)


_W: dict[str, Any] = {}


def _init() -> None:
    spec = importlib.util.spec_from_file_location("l1_build_base", L1 / "build_base.py")
    assert spec is not None and spec.loader is not None
    bb = importlib.util.module_from_spec(spec)
    sys.modules["l1_build_base"] = bb
    spec.loader.exec_module(bb)
    bb._init_worker()
    proxy = _HHProxy()
    bb.hh = proxy
    _W["bb"], _W["proxy"] = bb, proxy


def _one(job: tuple[dict, dict]) -> dict:
    bb, proxy = _W["bb"], _W["proxy"]
    proxy.last = None
    out = bb.build_one(job)
    rec = {"ticker": out["ticker"], "entry_date": out["entry_date"], "h_status": out["h_status"]}
    if out["h_status"] != "ok":
        return rec
    rec["H_corr"] = out["H_corr"]
    rec["m0"] = out["m0"]
    if int(out["n_hedge"]) == 0 or proxy.last is None:
        rec["kw"] = None
        return rec
    kw = proxy.last
    if kw.get("put_assigned_at") is not None or kw.get("financing") is None:
        raise AssertionError(f"last call is not the H_corr valuation for {rec}")
    rec["kw"] = kw
    return rec


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--workers", type=int, default=max(1, (os.cpu_count() or 2) - 4))
    a = ap.parse_args(argv)
    _init()
    bb = _W["bb"]
    base = pd.read_parquet(bb.BASE)
    f = pd.read_parquet(bb.FEATURES)
    for c in ("entry_date", "exit_date", "front_expiry"):
        f[c] = pd.to_datetime(f[c])
    base["entry_date"] = pd.to_datetime(base["entry_date"])
    f = f.drop_duplicates(["ticker", "entry_date"])
    m = base.merge(
        f, on=["ticker", "entry_date"], how="left", suffixes=("_b", ""), validate="one_to_one"
    )
    if a.limit:
        m = m.groupby("src", group_keys=False).head(a.limit)
    fcols = list(f.columns)
    jobs = [
        (
            {c: r[c] for c in fcols},
            {c: r[c] for c in ("ticker", "entry_date", "src", "H", "settle")},
        )
        for _, r in m.iterrows()
    ]
    print(f"jobs {len(jobs)}, workers {a.workers}", flush=True)
    t0 = time.time()
    with ProcessPoolExecutor(max_workers=a.workers, initializer=_init) as ex:
        res = list(ex.map(_one, jobs, chunksize=25))
    print(f"built in {time.time() - t0:.0f}s", flush=True)

    bc = pd.read_parquet(BASE_CORR)
    bc["entry_date"] = pd.to_datetime(bc["entry_date"])
    ref = bc.set_index(["ticker", "entry_date"])["H_corr"]
    n_ok = n_hedged = 0
    worst = 0.0
    for r in res:
        if r["h_status"] != "ok":
            continue
        n_ok += 1
        stored = float(ref.loc[(r["ticker"], pd.Timestamp(r["entry_date"]))])
        if abs(stored - r["H_corr"]) > TOL:
            raise AssertionError(f"rebuild differs from base_corrected for {r['ticker']}")
        if r["kw"] is None:
            continue
        n_hedged += 1
        again = hh_real.hedged_short_straddle(**r["kw"]).net_pnl / r["m0"]
        worst = max(worst, abs(again - stored))
    if worst > TOL:
        raise AssertionError(f"recorded inputs miss H_corr by {worst:.2e}")
    print(f"funnel: jobs {len(res)}, ok {n_ok}, hedged {n_hedged}, max gap {worst:.1e}")
    if a.limit:
        return
    OUT.parent.mkdir(exist_ok=True)
    tmp = OUT.with_suffix(".tmp")
    with open(tmp, "wb") as fh:
        pickle.dump(res, fh, protocol=pickle.HIGHEST_PROTOCOL)
    tmp.replace(OUT)
    print(f"wrote {OUT}")
    _ = np  # numpy kept for downstream unpickling of arrays


if __name__ == "__main__":
    main()
