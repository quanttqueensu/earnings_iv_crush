"""
b6_build.py
L2 idea B6: value the later-expiry straddle of every CRSP event under the H_corr conventions and
record both expiries' entry touch, so the per-event expiry choice can be scored. Declared in
diagnosis.log entry [6].

Usage
-----
    python outputs/research/2026-11-14-slate-tests/L2-execution/b6_build.py
    python outputs/research/2026-11-14-slate-tests/L2-execution/b6_build.py --limit 40

The later contract comes from the closed later-expiry study's ``later_row`` and is valued by L1's
``build_one``; both modules are imported, never edited. ``build_one`` checks its rebuild against
a stored H, so the later contract is first built once with the closed hedged-event-hold builder
and that H is passed in. Output: ``_cache/b6_later.parquet`` (temporary name, then renamed).
"""

from __future__ import annotations

import argparse
import importlib.util
import os
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

HERE = Path(__file__).resolve().parent
L1 = HERE.parent / "L1-corrections"
LATER = ROOT / "research" / "timing" / "2026-11-02-later-expiry-hedged-hold" / "study.py"
OUT = HERE / "_cache" / "b6_later.parquet"

_W: dict[str, Any] = {}


def _load(name: str, path: Path) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def _init() -> None:
    bb = _load("l1_build_base", L1 / "build_base.py")
    bb._init_worker()
    _W["bb"] = bb
    _W["le"] = _load("later_expiry_study", LATER)


def _one(frow: dict) -> dict:
    bb, le = _W["bb"], _W["le"]
    st = bb._W["st"]
    r = pd.Series(frow)
    key = {"ticker": r["ticker"], "entry_date": pd.Timestamp(r["entry_date"])}
    s, lr = le.later_row(r)
    if s != "ok" or lr is None:
        return {**key, "b6_status": s}
    st.CRSP_END = bb.CRSP_LAST
    b = st.build_event(lr, bb._W["crsp"])
    if b.get("status") != "ok":
        return {**key, "b6_status": f"L_{b.get('status')}"}
    brow = {
        "ticker": r["ticker"],
        "entry_date": key["entry_date"],
        "src": "crsp",
        "H": b["H"],
        "settle": b["settle"],
    }
    out = bb.build_one(({c: lr[c] for c in lr.index}, brow))
    if out.get("h_status") != "ok":
        return {**key, "b6_status": f"L1_{out.get('h_status')}"}
    keep = {k: v for k, v in out.items() if k.startswith(("H_", "c_")) or k in ("m0", "n_hedge")}
    return {
        **key,
        "b6_status": "ok",
        "L_expiry": lr["front_expiry"],
        "L_t": float(lr["front_t"]),
        "L_fwd": float(lr["front_fwd"]),
        "L_strike": float(lr["front_strike"]),
        "L_bid": float(lr["front_bid"]),
        "L_mid": float(lr["front_mid"]),
        "L_ask": float(lr["front_ask"]),
        "L_iv": float(lr["front_iv"]),
        **{f"L_{k}": v for k, v in keep.items()},
    }


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--workers", type=int, default=max(1, (os.cpu_count() or 2) - 4))
    a = ap.parse_args(argv)
    base = pd.read_parquet(L1 / "base_corrected.parquet")
    base["entry_date"] = pd.to_datetime(base["entry_date"])
    base = base[(base["src"] == "crsp") & (base["h_status"] == "ok")]
    f = pd.read_parquet(ROOT / "outputs" / "research" / "2026-10-20-hedged-hold" / "features.parquet")
    for c in ("entry_date", "exit_date", "front_expiry"):
        f[c] = pd.to_datetime(f[c])
    f = f.drop_duplicates(["ticker", "entry_date"])
    m = base[["ticker", "entry_date"]].merge(f, on=["ticker", "entry_date"], how="left")
    if m["front_fwd"].isna().any():
        raise ValueError("base events lack features")
    if a.limit:
        m = m.head(a.limit)
    jobs = [dict(r) for _, r in m.iterrows()]
    print(f"jobs {len(jobs)}, workers {a.workers}", flush=True)
    t0 = time.time()
    with ProcessPoolExecutor(max_workers=a.workers, initializer=_init) as ex:
        res = list(ex.map(_one, jobs, chunksize=20))
    print(f"built in {time.time() - t0:.0f}s", flush=True)
    d = pd.DataFrame(res)
    print("funnel:", dict(Counter(d["b6_status"]).most_common()), flush=True)
    if a.limit:
        print(d.head().T)
        return
    tmp = OUT.with_suffix(".tmp.parquet")
    d.to_parquet(tmp)
    tmp.replace(OUT)
    print(f"wrote {OUT} ({len(d)} rows)")
    _ = np


if __name__ == "__main__":
    main()
