"""
b6_score.py
L2 idea B6: per-event expiry choice. Sell the later expiry when its entry touch per unit of event
premium is lower than the front's; score the paired change in H_corr against always selling the
front. Declared in diagnosis.log entry [6].

Usage
-----
    python outputs/research/2026-11-14-slate-tests/L2-execution/b6_score.py --block 2013-18

Basis: per trade, USD per share divided by the front contract's m0 (both expiries on one
denominator), net at the touch. Reads ``_cache/b6_later.parquet`` from ``b6_build.py``.
"""

from __future__ import annotations

import argparse
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

import l2lib as L  # noqa: E402
from earnings_iv_crush.research.hedged_hold import straddle_value  # noqa: E402
from earnings_iv_crush.research.protocol import matched_random_null  # noqa: E402

LATER = L.HERE / "_cache" / "b6_later.parquet"
CLOSED = L.ROOT / "outputs" / "research" / "2026-11-02-later-expiry-hedged-hold" / "events.parquet"
FEATURES = L.ROOT / "outputs" / "research" / "2026-10-20-hedged-hold" / "features.parquet"
COMPONENTS = ("premium", "settlement", "hedge", "equity_cost", "fees", "disposal", "financing")


def event_premium(fwd: float, k: float, t: float, sd2: float, jv: float) -> float:
    """Straddle value with the event variance minus without it, USD per share."""
    return straddle_value(fwd, k, t, float(np.sqrt(sd2 + jv / t))) - straddle_value(
        fwd, k, t, float(np.sqrt(sd2))
    )


def load(block: str) -> pd.DataFrame:
    d = L.load_base()
    d = d[(d["block"] == block) & (d["h_status"] == "ok") & (d["src"] == "crsp")]
    lt = pd.read_parquet(LATER)
    lt["entry_date"] = pd.to_datetime(lt["entry_date"])
    f = pd.read_parquet(FEATURES).drop_duplicates(["ticker", "entry_date"])
    f["entry_date"] = pd.to_datetime(f["entry_date"])
    fc = ["front_t", "front_strike", "front_bid", "front_mid", "jsplit_sd2"]  # front_fwd in base
    fc += ["jsplit_jump_var"]
    f = f[["ticker", "entry_date", *fc]]
    m = d.merge(f, on=["ticker", "entry_date"], how="left", validate="one_to_one")
    m = m.merge(lt, on=["ticker", "entry_date"], how="left", validate="one_to_one")
    return m.reset_index(drop=True)


def reconcile(m: pd.DataFrame) -> dict:
    """The later contract's old-convention H against the closed study's stored L, in USD."""
    c = pd.read_parquet(CLOSED)
    c["entry_date"] = pd.to_datetime(c["entry_date"])
    j = m[m["b6_status"] == "ok"].merge(c, on=["ticker", "entry_date"], suffixes=("", "_c"))
    s0 = j["c_premium"] * j["m0"]
    mc = 0.20 * j["front_fwd"] + np.maximum(s0, j["L_bid"])
    gap = (j["L_H_rebuilt"] * j["L_m0"] - j["L"] * mc).abs() / j["m0"]
    return {"n": int(len(j)), "max_gap_m0": float(gap.max()), "share_over_1e-9": float((gap > 1e-9).mean())}


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--block", required=True, choices=("2013-18", "2019-24"))
    a = ap.parse_args(argv)
    m = load(a.block)
    funnel = Counter(m["b6_status"].fillna("not_built"))
    print(f"{a.block}: events {len(m)}; later-contract funnel {dict(funnel)}")
    ok = m["b6_status"].eq("ok")
    rec = reconcile(m)
    print(f"  reconciliation to the closed later-expiry study: {rec}")
    if rec["max_gap_m0"] > 1e-9:
        raise AssertionError("later contract does not reproduce the closed study's L")
    valid = ok & (m["jsplit_sd2"] > 0) & (m["jsplit_jump_var"] > 0)
    print(f"  split valid with a later contract: {int(valid.sum())} of {len(m)}")
    ratio_f = np.full(len(m), np.nan)
    ratio_l = np.full(len(m), np.nan)
    for i in np.flatnonzero(valid.to_numpy()):
        r = m.iloc[i]
        ep_f = event_premium(r["front_fwd"], r["front_strike"], r["front_t"], r["jsplit_sd2"],
                             r["jsplit_jump_var"])
        ep_l = event_premium(r["L_fwd"], r["L_strike"], r["L_t"], r["jsplit_sd2"],
                             r["jsplit_jump_var"])
        if ep_f > 0 and ep_l > 0:
            ratio_f[i] = (r["front_mid"] - r["front_bid"]) / ep_f
            ratio_l[i] = (r["L_mid"] - r["L_bid"]) / ep_l
    pick = np.isfinite(ratio_l) & np.isfinite(ratio_f) & (ratio_l < ratio_f)
    m0 = m["m0"].to_numpy()
    d_all = np.where(ok, (m["L_H_corr"] * m["L_m0"] - m["H_corr"] * m0) / m0, np.nan)
    gain = np.where(pick, d_all, 0.0)
    dates = m["exit_date"]
    res: dict = {"block": a.block, "n_events": len(m), "funnel": dict(funnel), "reconcile": rec}
    res["n_valid"] = int(valid.sum())
    res["n_later_chosen"] = int(pick.sum())
    res["share_later"] = float(pick.mean())
    res["primary_paired_mean"] = L.iv_dict(L.mean_ci(gain, dates))
    pop = np.where(ok, d_all, np.nan)
    sel = pick[ok.to_numpy()]
    popo = pop[ok.to_numpy()]
    n_pop = len(m)
    nul = matched_random_null(popo, sel, lambda x: float(np.nansum(x)) / n_pop)
    res["null"] = {
        "observed": nul.observed * 100,
        "null_median": float(np.nanmedian(nul.null)) * 100,
        "null_p95": float(np.nanpercentile(nul.null, 95)) * 100,
        "percentile": nul.percentile,
    }
    res["always_later_paired_mean"] = L.iv_dict(L.mean_ci(d_all[ok.to_numpy()], dates[ok]))
    res["level_front"] = L.iv_dict(L.mean_ci(m["H_corr"], dates))
    res["level_chosen"] = L.iv_dict(L.mean_ci(m["H_corr"].to_numpy() + gain, dates))
    dec = {}
    for c in COMPONENTS:
        dc = np.where(pick, (m[f"L_c_{c}"] * m["L_m0"] - m[f"c_{c}"] * m0) / m0, 0.0)
        dec[c] = float(np.nanmean(dc[pick]) * 100) if pick.any() else None
    res["decomposition_on_switched"] = dec
    res["gain_on_switched"] = float(np.mean(gain[pick]) * 100) if pick.any() else None
    tf = (m["front_mid"] - m["front_bid"]) / m0
    tl = (m["L_mid"] - m["L_bid"]) / m0
    res["touch_on_switched"] = {
        "front": float(tf[pick].mean() * 100),
        "later": float(tl[pick].mean() * 100),
    }
    print(f"  later chosen {int(pick.sum())}; primary {L.fmt(L.mean_ci(gain, dates))}")
    print(f"  null {res['null']}")
    print(f"  decomposition on switched (% of front m0): {dec}")
    L.write_json(L.HERE / f"b6_{a.block}.json", res)
    L.record_view(a.block, "execution_expiry_choice", "L2-execution b6_score.py")
    print(f"wrote b6_{a.block}.json")


if __name__ == "__main__":
    main()
