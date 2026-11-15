"""c8_megacap_panel.py: the megacap hedged-hold panel re-settled on L1's corrected conventions.

The 1,183 valued events of ``2026-11-02-hedged-event-hold/events_megacap.parquet`` are not in
``base_corrected`` (which holds the broad panel). Each event's front row is rebuilt by the closed
megacap amendment's own ``megacap.front_row`` from the megacap 15:59 strips, the study's exit
readers are switched to ``megacap.exit_quotes`` and ``megacap.exit_fwd`` exactly as
``megacap.main`` does, and the event is passed through L1's ``build_base.build_one`` (imported,
never edited), which rebuilds the stored H through the closed study's own builder and keeps an event only if it reproduces (``h_status == "ok"``), then values
H_net, H_corr and the residual value exactly as for the broad panel. Writes
``c8_megacap_corrected.parquet`` with the funnel. No selector is read here.

Usage
-----
    python outputs/research/2026-11-14-slate-tests/L3-selection/c8_megacap_panel.py
"""

from __future__ import annotations

import importlib.util
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from typing import Any

import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from lib import ROOT  # noqa: E402

BB_PATH = HERE.parent / "L1-corrections" / "build_base.py"
MEGA_PY = ROOT / "research" / "timing" / "2026-11-02-hedged-event-hold" / "megacap.py"
MEGA = ROOT / "outputs" / "research" / "2026-11-02-hedged-event-hold" / "events_megacap.parquet"
OUT = HERE / "c8_megacap_corrected.parquet"
_BB: Any = None


def _init() -> None:
    global _BB
    spec = importlib.util.spec_from_file_location("l1_build_base", BB_PATH)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules["l1_build_base"] = mod
    spec.loader.exec_module(mod)
    mod._init_worker()
    spec2 = importlib.util.spec_from_file_location("megacap_amendment", MEGA_PY)
    assert spec2 is not None and spec2.loader is not None
    mc = importlib.util.module_from_spec(spec2)
    sys.modules["megacap_amendment"] = mc
    spec2.loader.exec_module(mc)
    for target in (mod._W["st"], sys.modules["hh_study"]):
        target.exit_quotes, target.exit_fwd = mc.exit_quotes, mc.exit_fwd
    mod._W["mc"] = mc
    _BB = mod


def _front(job: tuple[dict, dict]) -> tuple[dict, dict] | None:
    fr = _BB._W["mc"].front_row(pd.Series(job[0]))
    return None if fr is None else (fr.to_dict(), job[1])


def one(job: tuple[dict, dict]) -> dict:
    fj = _front(job)
    if fj is None:
        return {
            "ticker": job[1]["ticker"],
            "entry_date": job[1]["entry_date"],
            "h_status": "no_entry_front",
        }
    return _BB.build_one(fj)


def main() -> None:
    _init()
    m = pd.read_parquet(MEGA)
    print(f"megacap events {len(m)}; valued (status ok) {(m['status'] == 'ok').sum()}")
    m = m[m["status"] == "ok"].copy()
    m["src"] = "crsp"
    f = pd.read_parquet(_BB.FEATURES)[["ticker", "entry_date", "permno", "s2_iv"]]
    f["entry_date"] = pd.to_datetime(f["entry_date"])
    f = f.drop_duplicates(["ticker", "entry_date"])
    j = m.drop(columns=["permno"], errors="ignore").merge(
        f, on=["ticker", "entry_date"], how="left", validate="one_to_one"
    )
    if j["permno"].isna().any():
        raise ValueError("valued megacap events lack a permno")
    j["exit_date"] = pd.to_datetime(j["exit_date"])
    fcols = ["ticker", "entry_date", "exit_date", "permno", "s2_iv"]
    jobs = [
        (
            {c: r[c] for c in fcols},
            {c: r[c] for c in ("ticker", "entry_date", "src", "H", "settle")},
        )
        for _, r in j.iterrows()
    ]
    with ProcessPoolExecutor(max_workers=6, initializer=_init) as ex:
        res = pd.DataFrame(list(ex.map(one, jobs, chunksize=20)))
    print("funnel (h_status):")
    print(res["h_status"].value_counts().to_string())
    print("residual value marks:", res["rv_status"].value_counts().to_dict())
    keep = ["ticker", "entry_date", "exit_date", "expiry", "H", "B", "permno"]
    out = (
        j[keep]
        .reset_index(drop=True)
        .merge(
            res.drop(columns=[c for c in ("m0", "s0", "strike", "settle") if c in res]),
            on=["ticker", "entry_date"],
            how="left",
            validate="one_to_one",
        )
    )
    out = out.merge(j[["ticker", "entry_date", "m0"]], on=["ticker", "entry_date"])
    out["year"] = pd.to_datetime(out["entry_date"]).dt.year
    print(f"max reproduction gap on ok rows: {out.loc[out['h_status'] == 'ok', 'repro_gap'].max()}")
    tmp = OUT.with_suffix(".tmp")
    out.to_parquet(tmp)
    tmp.replace(OUT)
    print(f"wrote {OUT} ({len(out)} rows)")


if __name__ == "__main__":
    main()
