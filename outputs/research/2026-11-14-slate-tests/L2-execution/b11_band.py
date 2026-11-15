"""
b11_band.py
L2 idea B11: the delta band with stock commission. The hedge is re-set to the Black-Scholes
target only when it has drifted more than a band from the position held (always set at the
reaction close; the netted expiry residual always trades), and every nonzero stock order pays
IBKR Tiered with the 1% cap (recalled). Both arms pay the same commission, so the comparison is
like for like. Declared in diagnosis.log entry [23]; nearest closed study laneA-hold-exit 1,787.

Usage
-----
    python outputs/research/2026-11-14-slate-tests/L2-execution/b11_band.py --block 2013-18
    python outputs/research/2026-11-14-slate-tests/L2-execution/b11_band.py --block 2019-24

On 2013-18 every band in ``delta_band_grid`` is scored and the champion is chosen by the
1-contract paired mean. Any other block scores only band 0 and the champion recorded in
``b11_2013-18.json``, and refuses to run unless ``freeze_b11_band.md`` verifies.
Output: ``b11_<block>.json``.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import l2fees as F  # noqa: E402
import l2lib as L  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from earnings_iv_crush.config import EXECUTION_LEVERS as XL  # noqa: E402
from earnings_iv_crush.research import hedged_hold as hh  # noqa: E402

DISCOVERY = "2013-18"
FREEZE = L.HERE / "freeze_b11_band.md"


def event_band(kw: dict, band: float) -> dict:
    """Banded valuation of one event in USD per share, with commission at each contract size."""
    h = F.banded(kw, band)
    r = hh.hedged_short_straddle(**kw, hedge_ratios=h)
    t = F.traded_for(kw, h)
    px = F.order_prices(kw)
    out = {"net": r.net_pnl, "hedge": r.hedge_pnl, "eq": r.equity_cost}
    for nc in XL.commission_contract_sizes:
        comm, n_ord, _ = F.stock_commission(t, px, nc)
        out[f"comm_{nc}"] = comm
        out[f"orders_{nc}"] = n_ord
    return out


def build(d: pd.DataFrame, bands: tuple[float, ...]) -> pd.DataFrame:
    """Per-event, per-band rows; unhedged events carry the same zero-order row for every band."""
    paths = L.load_paths()
    rows = []
    for _, r in d.iterrows():
        kw = paths[(r["ticker"], r["entry_date"])]["kw"]
        for b in bands:
            base = {"key": (r["ticker"], r["entry_date"]), "band": b, "m0": r["m0"]}
            base["date"] = r["exit_date"]
            if kw is None:
                z = {"net": r["H_corr"] * r["m0"], "hedge": 0.0, "eq": 0.0}
                for nc in XL.commission_contract_sizes:
                    z[f"comm_{nc}"], z[f"orders_{nc}"] = 0.0, 0
                rows.append({**base, **z, "H_corr": r["H_corr"]})
            else:
                rows.append({**base, **event_band(kw, b), "H_corr": r["H_corr"]})
    e = pd.DataFrame(rows)
    e["date"] = pd.to_datetime(e["date"])
    b0 = e[e["band"] == 0.0]
    gap = float(np.max(np.abs(b0["net"] / b0["m0"] - b0["H_corr"])))
    print(f"check: band 0 reproduces H_corr, max gap {gap:.2e} (fraction of m0), N {len(b0)}")
    if gap > 1e-9:
        raise AssertionError("band 0 does not reproduce H_corr")
    return e


def score(e: pd.DataFrame, band: float) -> dict:
    """Paired like-for-like statistics of one band against band 0."""
    a = e[e["band"] == band].set_index("key")
    z = e[e["band"] == 0.0].set_index("key").loc[a.index]
    m0, dates = a["m0"].to_numpy(), a["date"]
    out: dict = {"band": band, "N": len(a), "dates": int(dates.nunique())}
    for nc in XL.commission_contract_sizes:
        ha = (a["net"] - a[f"comm_{nc}"]) / m0
        h0 = (z["net"] - z[f"comm_{nc}"]) / m0
        out[f"paired_N{nc}"] = L.iv_dict(L.mean_ci(ha.to_numpy() - h0.to_numpy(), dates))
        out[f"var_ratio_N{nc}"] = L.iv_dict(L.var_ratio_ci(ha, h0, dates), scale=1.0)
        out[f"level_band_N{nc}"] = L.iv_dict(L.mean_ci(ha, dates))
        out[f"level_band0_N{nc}"] = L.iv_dict(L.mean_ci(h0, dates))
        out[f"commission_saved_N{nc}"] = L.iv_dict(
            L.mean_ci((z[f"comm_{nc}"] - a[f"comm_{nc}"]).to_numpy() / m0, dates)
        )
        out[f"orders_per_event_N{nc}"] = float(a[f"orders_{nc}"].mean())
        out[f"orders_per_event_band0_N{nc}"] = float(z[f"orders_{nc}"].mean())
    out["equity_cost_saved"] = L.iv_dict(L.mean_ci((z["eq"] - a["eq"]).to_numpy() / m0, dates))
    out["hedge_pnl_change"] = L.iv_dict(L.mean_ci((a["hedge"] - z["hedge"]).to_numpy() / m0, dates))
    out["net_before_commission_change"] = L.iv_dict(
        L.mean_ci((a["net"] - z["net"]).to_numpy() / m0, dates)
    )
    return out


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--block", required=True, choices=L.BLOCKS)
    args = ap.parse_args(argv)
    d = L.load_base()
    d = d[(d["block"] == args.block) & (d["h_status"] == "ok")].reset_index(drop=True)
    if args.block == DISCOVERY:
        bands = tuple(XL.delta_band_grid)
    else:
        if not (FREEZE.exists() and L.verify_freeze(FREEZE)):
            raise SystemExit("freeze_b11_band.md missing or does not verify; no held-out read")
        disc = json.loads((L.HERE / f"b11_{DISCOVERY}.json").read_text())
        bands = (0.0, float(disc["champion"]))
    print(f"{args.block}: base ok {len(d)}; bands {bands}")
    e = build(d, bands)
    res: dict = {"block": args.block, "n_events": len(d), "bands": {}}
    for b in bands:
        if b == 0.0:
            continue
        res["bands"][str(b)] = s = score(e, b)
        print(f"band {b}: paired N1 {s['paired_N1']}, var ratio N1 {s['var_ratio_N1']}")
    if args.block == DISCOVERY:
        best = max(res["bands"].values(), key=lambda s: s["paired_N1"]["point"])
        res["champion"] = best["band"]
    L.write_json(L.HERE / f"b11_{args.block}.json", res)
    kind = "trial" if args.block != "2025-26" else "exploratory"
    L.record_view(args.block, "execution_delta_band_commission", "L2-execution b11_band.py", kind)


if __name__ == "__main__":
    main()
