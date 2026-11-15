"""
reconcile.py
Reconcile the package's assignment netting (``HEDGED_NET``) to the stored hedged-hold table and
to lane A's independent check, on the real events of the 2026-11-02 hedged-event-hold study.

The closed study's own ``build_event`` runs unchanged; only its reference to
``hedged_short_straddle`` is wrapped so that each hedged event is valued under both settlement
conventions. Under ``HEDGED`` the rebuilt H must equal the stored H exactly, which proves the
rebuild is the study; the difference to ``HEDGED_NET`` is then the correction, per event.
Descriptive, not a trial. Reads cached chains and CRSP only.

Usage
-----
    python outputs/research/2026-11-13-alpha-hunt-2/netting_reconciliation/reconcile.py
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))

from earnings_iv_crush.config import HEDGED, HEDGED_NET  # noqa: E402
from earnings_iv_crush.research import hedged_hold as hh  # noqa: E402
from earnings_iv_crush.research.protocol import date_clustered_ci  # noqa: E402

HERE = Path(__file__).resolve().parent
STUDY = ROOT / "research" / "timing" / "2026-11-02-hedged-event-hold" / "study.py"
STORED = ROOT / "outputs" / "research" / "2026-11-02-hedged-event-hold" / "events.parquet"
BLOCKS = ((2013, 2018), (2019, 2024), (2025, 2026))


def _load_study() -> Any:
    spec = importlib.util.spec_from_file_location("hedged_event_hold_study", STUDY)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.path.insert(0, str(STUDY.parent))
    spec.loader.exec_module(mod)
    return mod


def main() -> None:
    st = _load_study()
    last: dict[str, float] = {}

    def both(**kw: Any) -> hh.HedgedResult:
        old = hh.hedged_short_straddle(**kw, cfg=HEDGED)
        if kw.get("hedge", True):
            last["net"] = hh.hedged_short_straddle(**kw, cfg=HEDGED_NET).net_pnl
        return old

    st.hedged_short_straddle = both
    f = pd.read_parquet(st.FEATURES)
    for c in ("entry_date", "exit_date", "front_expiry"):
        f[c] = pd.to_datetime(f[c])
    crsp = st.load_crsp()
    rows = []
    for i, (_, r) in enumerate(f.iterrows()):
        last.clear()
        out = st.build_event(r, crsp)
        if out.get("status") == "ok":
            out["H_net"] = last["net"] / out["m0"] if "net" in last else out["H"]
        rows.append(out)
        if (i + 1) % 1000 == 0:
            print(f"  built {i + 1}/{len(f)}", flush=True)
    d = pd.DataFrame(rows)
    d = d[d["status"] == "ok"].copy()
    d["gain"] = d["H_net"] - d["H"]

    stored = pd.read_parquet(STORED)
    stored = stored[stored["status"] == "ok"][["ticker", "entry_date", "H"]]
    m = d.merge(stored, on=["ticker", "entry_date"], suffixes=("", "_stored"), validate="1:1")
    gap = float(np.max(np.abs(m["H"] - m["H_stored"])))
    print(f"rebuild vs stored H: N {len(m)} of {len(d)} rebuilt ok, max abs gap {gap:.2e} of m0")
    if gap > 1e-9:
        raise ValueError("the rebuild does not reproduce the stored H; the comparison is void")

    d["year"] = pd.to_datetime(d["entry_date"]).dt.year
    hedged = d["n_hedge"] > 0
    print(f"events with no hedging session (no netting possible): {int((~hedged).sum())}")
    print(f"share of hedged events where netting costs more: {float((d.loc[hedged, 'gain'] < 0).mean()):.3f}")
    mean = lambda a: float(np.mean(a))  # noqa: E731
    for y0, y1 in BLOCKS:
        b = d[(d["year"] >= y0) & (d["year"] <= y1)]
        if b.empty:
            continue
        dates = pd.to_datetime(b["exit_date"])
        g = date_clustered_ci(b["gain"].to_numpy(float), dates, mean)
        h0 = date_clustered_ci(b["H"].to_numpy(float), dates, mean)
        h1 = date_clustered_ci(b["H_net"].to_numpy(float), dates, mean)
        print(
            f"{y0}-{y1} N {len(b)} | gain {g.point:+.4%} [{g.low:+.4%}, {g.high:+.4%}] | "
            f"H {h0.point:+.4%} [{h0.low:+.4%}, {h0.high:+.4%}] -> "
            f"H_net {h1.point:+.4%} [{h1.low:+.4%}, {h1.high:+.4%}]"
        )
    d[["ticker", "entry_date", "exit_date", "n_hedge", "H", "H_net", "gain"]].to_parquet(
        HERE / "netting_by_event.parquet"
    )


if __name__ == "__main__":
    main()
