"""
score.py
Lane B scorer: paired contract-choice variants against the frozen hedged ATM straddle hold (H) on
the same events, unit base m0 (or own margin where stated), net at the touch, per trade.

Usage
-----
    python outputs/research/2026-11-13-alpha-hunt-2/laneB-contract-choice/score.py BLOCK ID [ID ...]

BLOCK is ``disc`` (entry years 2013-18) or ``held`` (2019-24). Each (trial id, block) pair is
appended to ``trials.csv`` once; a rerun prints but never rewrites a logged row.
"""

from __future__ import annotations

import csv
import os
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from earnings_iv_crush.research.protocol import (  # noqa: E402
    date_clustered_ci,
    matched_random_null,
)

HERE = Path(__file__).resolve().parent
TRIALS = HERE / "trials.csv"
COLS = [
    "trial_id",
    "hypothesis",
    "mechanism",
    "block",
    "N",
    "effect",
    "ci_low",
    "ci_high",
    "t",
    "null_percentile",
    "basis",
    "verdict",
]
BLOCKS = {"disc": (2013, 2018), "held": (2019, 2024)}
SEED, N_DRAWS = 0, 5000
MARGIN_SPOT_FRAC = 0.20


def _mean(a: np.ndarray) -> float:
    return float(np.mean(a))


def ci(x: pd.Series, dates: pd.Series) -> dict:
    iv = date_clustered_ci(x.to_numpy(float), dates, _mean)
    se = (iv.high - iv.low) / 3.92
    return {
        "point": iv.point,
        "low": iv.low,
        "high": iv.high,
        "n": iv.n,
        "t": iv.point / se if se > 0 else np.nan,
    }


def load() -> pd.DataFrame:
    d = pd.read_parquet(HERE / os.environ.get("LANEB_ARMS", "arms.parquet"))
    d["year"] = pd.to_datetime(d["entry_date"]).dt.year
    d["exit_date"] = pd.to_datetime(d["exit_date"])
    d["im"] = d["mid0"] / d["fwd"]
    for lab in ("k0", "km1", "kp1"):
        d[f"{lab}_ok"] = d[f"{lab}_status"].eq("ok")
        d[f"{lab}_spr"] = d[f"{lab}_ask"] - d[f"{lab}_bid"]
        d[f"{lab}_g"] = (d[f"{lab}_usd"] - d["k0_usd"]) / d["m0"]  # switch gain, base m0
        d[f"{lab}_gmid"] = (d[f"{lab}_usd_mid"] - d["k0_usd_mid"]) / d["m0"]
        d[f"{lab}_hs_saved"] = (
            (d["k0_mid"] - d["k0_bid"]) - (d[f"{lab}_mid"] - d[f"{lab}_bid"])
        ) / d["m0"]
    # neighbour on the other side of the forward from the ATM strike
    other_lo = d["k0"] > d["fwd"]
    d["nb"] = np.where(other_lo, "km1", "kp1")
    return d


CRSP = ROOT / "outputs" / "research" / "2026-10-20-hedged-hold" / "crsp_paths.parquet"
EQ_FLOOR = 1e-4  # the frozen equity half-spread floor (HEDGED.equity_cost_floor_bps = 1 bp)


def add_entry_night_hedge(d: pd.DataFrame) -> pd.DataFrame:
    """Delta-match each alternative strike to the ATM straddle over the unhedged event night.

    Holds (delta_alt - delta_0) shares from the entry-session close to the reaction-session
    close (CRSP), paying the CRSP closing half-spread (floored at 1 bp) on both trades, so the
    switch gain loses its first-order directional component. Deltas: Black-Scholes straddle
    delta on the entry parity forward with each strike's own 15:59 mid IV. The options are sold
    at 15:59 and the stock trades at the 16:00 close, a one-minute mismatch.
    """
    from earnings_iv_crush.research.hedged_hold import straddle_delta

    c = pd.read_parquet(CRSP, columns=["permno", "date", "prc", "ret", "bid", "ask"])
    c["date"] = pd.to_datetime(c["date"])
    for col in ("prc", "ret", "bid", "ask"):
        c[col] = pd.to_numeric(c[col], errors="coerce").astype(float)
    c["prc"] = c["prc"].abs()  # CRSP marks a bid-ask midpoint close with a negative sign
    c["hs"] = ((c["ask"] - c["bid"]) / 2 / c["prc"]).clip(lower=EQ_FLOOR)
    c = c.set_index(["permno", "date"]).sort_index()
    pe = pd.MultiIndex.from_arrays([d["permno"].astype(int), pd.to_datetime(d["entry_date"])])
    px = pd.MultiIndex.from_arrays([d["permno"].astype(int), pd.to_datetime(d["exit_date"])])
    s_e = c["prc"].reindex(pe).to_numpy()
    hs_e = c["hs"].reindex(pe).to_numpy()
    r_x = c["ret"].reindex(px).to_numpy(dtype=float)
    p_x = c["prc"].reindex(px).to_numpy()
    hs_x = c["hs"].reindex(px).to_numpy()
    d["s_entry"], d["r_react"] = s_e, r_x
    d["hs_e"], d["p_x"], d["hs_x"] = hs_e, p_x, hs_x
    for lab in ("k0", "km1", "kp1"):
        d[f"{lab}_delta"] = [
            straddle_delta(f, k, t, s) if np.isfinite(k) and np.isfinite(s) else np.nan
            for f, k, t, s in zip(d["fwd"], d[f"{lab}_K"], d["t0"], d[f"{lab}_mid_iv"])
        ]
    for lab in ("km1", "kp1"):
        x = d[f"{lab}_delta"] - d["k0_delta"]
        pnl = x * s_e * r_x - x.abs() * (s_e * hs_e + p_x * hs_x)
        d[f"{lab}_gdn"] = d[f"{lab}_g"] + pnl / d["m0"]
    print(
        "  entry-night hedge coverage: "
        f"{int(np.isfinite(d['km1_gdn']).sum())} km1, {int(np.isfinite(d['kp1_gdn']).sum())} kp1 "
        f"of {len(d)}; missing reaction return {int(np.isnan(r_x).sum())}"
    )
    return d


def funnel_check(d: pd.DataFrame, elig: pd.Series, name: str) -> dict:
    cov, unc = d.loc[elig, "H"], d.loc[~elig, "H"]
    out = {
        "n_block": int(len(d)),
        "n_eligible": int(elig.sum()),
        "H_covered": float(cov.mean()),
        "H_uncovered": float(unc.mean()) if len(unc) else None,
        "n_uncovered": int(len(unc)),
    }
    print(f"  funnel {name}: {out}")
    return out


# ── strike rules ────────────────────────────────────────────────────────────


def _pick(d: pd.DataFrame, cands: list[str], key: str, better: str) -> pd.Series:
    """Label of the chosen strike per event; K0 unless a candidate is strictly better."""
    best = pd.Series("k0", index=d.index)
    bestv = d[f"k0_{key}"].copy()
    for lab in cands:
        v = d[f"{lab}_{key}"]
        ok = d[f"{lab}_ok"] & v.notna()
        imp = (v < bestv - 1e-9) if better == "min" else (v > bestv + 1e-9)
        m = ok & imp
        best[m], bestv[m] = lab, v[m]
    return best


def _custom_null(d: pd.DataFrame, cands: list[str], k: int, n: int, gcol: str = "g") -> np.ndarray:
    """Switch k random eligible events to a random available neighbour; stat = sum / n."""
    g = np.column_stack([d[f"{c}_{gcol}"].to_numpy(float) for c in cands])
    ok = np.column_stack([d[f"{c}_ok"].to_numpy(bool) for c in cands]) & np.isfinite(g)
    rng = np.random.default_rng(SEED)
    out = np.empty(N_DRAWS)
    for b in range(N_DRAWS):
        idx = rng.choice(len(d), size=k, replace=False)
        tot = 0.0
        for i in idx:
            av = np.flatnonzero(ok[i])
            if av.size:
                tot += g[i, rng.choice(av)]
        out[b] = tot / n
    return out


def strike_rule(d: pd.DataFrame, cands_mode: str, key: str, better: str, gcol: str = "g") -> dict:
    if cands_mode == "bracket":
        elig = d["k0_ok"] & (
            ((d["nb"] == "km1") & d["km1_ok"]) | ((d["nb"] == "kp1") & d["kp1_ok"])
        )
    else:
        elig = d["k0_ok"] & (d["km1_ok"] | d["kp1_ok"])
    fc = funnel_check(d, elig, cands_mode)
    e = d[elig].copy()
    if cands_mode == "bracket":
        # one candidate per event: the neighbour across the forward
        for lab in ("km1", "kp1"):
            e.loc[e["nb"] != lab, f"{lab}_ok"] = False
    choice = _pick(e, ["km1", "kp1"], key, better)
    gain = pd.Series(0.0, index=e.index)
    hs = pd.Series(0.0, index=e.index)
    gm = pd.Series(0.0, index=e.index)
    for lab in ("km1", "kp1"):
        m = choice == lab
        gain[m], hs[m], gm[m] = e.loc[m, f"{lab}_{gcol}"], e.loc[m, f"{lab}_hs_saved"], e.loc[
            m, f"{lab}_gmid"
        ]
    sw = choice != "k0"
    k, n = int(sw.sum()), len(e)
    if cands_mode == "bracket":
        pop = np.where(e["nb"] == "km1", e[f"km1_{gcol}"], e[f"kp1_{gcol}"]).astype(float)
        nul = matched_random_null(pop, sw.to_numpy(), lambda x: float(np.nansum(x)) / n,
                                  n_draws=N_DRAWS, seed=SEED)
        pct, nmed = nul.percentile, float(np.nanmedian(nul.null))
    else:
        nd = _custom_null(e, ["km1", "kp1"], k, n, gcol)
        pct, nmed = float(100 * (nd < gain.sum() / n).mean()), float(np.median(nd))
    r = ci(gain, e["exit_date"])
    lvl = ci(e["H"] + gain, e["exit_date"])
    return {
        "res": r,
        "null_pct": pct,
        "null_median": nmed,
        "share_switched": k / n,
        "level_chosen": lvl,
        "level_H_same": float(e["H"].mean()),
        "gain_on_switched": float(gain[sw].mean()) if k else None,
        "decomp_on_switched": {
            "entry_half_spread_saved": float(hs[sw].mean()) if k else None,
            "mid_pnl_gain": float(gm[sw].mean()) if k else None,
        },
        "funnel": fc,
    }


def always_neighbour(d: pd.DataFrame, gcol: str = "g") -> dict:
    nbg = np.where(d["nb"] == "km1", d[f"km1_{gcol}"], d[f"kp1_{gcol}"])
    nbok = np.where(d["nb"] == "km1", d["km1_ok"], d["kp1_ok"]).astype(bool)
    elig = pd.Series(nbok & d["k0_ok"].to_numpy(), index=d.index) & np.isfinite(nbg)
    fc = funnel_check(d, elig, "always_neighbour")
    e = d[elig]
    g = pd.Series(nbg[elig.to_numpy()], index=e.index)
    hs = pd.Series(
        np.where(e["nb"] == "km1", e["km1_hs_saved"], e["kp1_hs_saved"]), index=e.index
    )
    gm = pd.Series(np.where(e["nb"] == "km1", e["km1_gmid"], e["kp1_gmid"]), index=e.index)
    return {
        "res": ci(g, e["exit_date"]),
        "null_pct": None,
        "level_chosen": ci(e["H"] + g, e["exit_date"]),
        "level_H_same": float(e["H"].mean()),
        "decomp": {"entry_half_spread_saved": float(hs.mean()), "mid_pnl_gain": float(gm.mean())},
        "funnel": fc,
    }


def legs_rule(d: pd.DataFrame, dm: bool = False) -> dict:
    """1818: per-leg tightest quote on the two bracketing strikes, against build_g's ATM."""
    lg = pd.read_parquet(HERE / "legs.parquet")
    lg["entry_date"] = pd.to_datetime(lg["entry_date"])
    e = d.merge(lg, on=["ticker", "entry_date"], how="left", suffixes=("", "_l"))
    base = np.where(e["k0"] == e["k_lo"], "ll", np.where(e["k0"] == e["k_hi"], "hh", ""))
    labs = ["ll", "hh", "hl", "lh"]
    ok = {c: e[f"{c}_status"].eq("ok").to_numpy() for c in labs}
    elig = pd.Series(
        (base != "") & e["lstatus"].eq("ok").to_numpy() & np.all([ok[c] for c in labs], axis=0),
        index=e.index,
    )
    fc = funnel_check(e, elig, "legs")
    e = e[elig].copy()
    base = base[elig.to_numpy()]
    usd = {c: e[f"{c}_usd"].to_numpy(float) for c in labs}
    if dm:
        dl = {}
        for r in "CP":
            for sd in ("lo", "hi"):
                dl[(r, sd)] = np.array([
                    _leg_delta((b + a) / 2, f, k, t, r)
                    for b, a, f, k, t in zip(e[f"{r}{sd}_bid"], e[f"{r}{sd}_ask"], e["fwd"],
                                             e[f"k_{sd}"], e["t0"])
                ])
        cdel = {c: dl[("C", {"l": "lo", "h": "hi"}[c[0]])] + dl[("P", {"l": "lo", "h": "hi"}[c[1]])]
                for c in labs}
        b_del = np.array([cdel[b][i] for i, b in enumerate(base)])
        se, rx = e["s_entry"].to_numpy(float), e["r_react"].to_numpy(float)
        cst = (se * e["hs_e"].to_numpy(float) + e["p_x"].to_numpy(float) * e["hs_x"].to_numpy(float))
        for c in labs:
            x = cdel[c] - b_del
            usd[c] = usd[c] + x * se * rx - np.abs(x) * cst
    b_usd = np.array([usd[b][i] for i, b in enumerate(base)])
    side0 = np.where(base == "ll", "lo", "hi")
    spr = {
        (r, s): (e[f"{r}{s}_ask"] - e[f"{r}{s}_bid"]).to_numpy(float)
        for r in "CP"
        for s in ("lo", "hi")
    }

    def pick(r: str) -> np.ndarray:
        other = np.where(side0 == "lo", "hi", "lo")
        s0 = np.array([spr[(r, a)][i] for i, a in enumerate(side0)])
        s1 = np.array([spr[(r, a)][i] for i, a in enumerate(other)])
        return np.where(s1 < s0 - 1e-9, other, side0)

    cs, ps = pick("C"), pick("P")
    chosen = np.array([{"lolo": "ll", "hihi": "hh", "hilo": "hl", "lohi": "lh"}[a + b]
                       for a, b in zip(cs, ps)])
    ch_usd = np.array([usd[c][i] for i, c in enumerate(chosen)])
    gain = pd.Series((ch_usd - b_usd) / e["m0"].to_numpy(), index=e.index)
    vs_h = pd.Series(ch_usd / e["m0"].to_numpy() - e["H"].to_numpy(), index=e.index)
    sw = chosen != base
    k, n = int(sw.sum()), len(e)
    rng = np.random.default_rng(SEED)
    g_all = np.column_stack([(usd[c] - b_usd) / e["m0"].to_numpy() for c in labs])
    is_base = np.column_stack([base == c for c in labs])
    nd = np.empty(N_DRAWS)
    for b in range(N_DRAWS):
        idx = rng.choice(n, size=k, replace=False)
        tot = 0.0
        for i in idx:
            av = np.flatnonzero(~is_base[i] & np.isfinite(g_all[i]))
            if av.size:
                tot += g_all[i, rng.choice(av)]
        nd[b] = tot / n
    pct = float(100 * (nd < gain.sum() / n).mean())
    return {
        "res": ci(gain, e["exit_date"]),
        "vs_stored_H": ci(vs_h, e["exit_date"]),
        "null_pct": pct,
        "null_median": float(np.median(nd)),
        "share_switched": k / n,
        "choice_counts": pd.Series(chosen).value_counts().to_dict(),
        "base_counts": pd.Series(base).value_counts().to_dict(),
        "level_chosen": ci(pd.Series(ch_usd / e["m0"].to_numpy(), index=e.index), e["exit_date"]),
        "level_base_buildg": float((b_usd / e["m0"].to_numpy()).mean()),
        "level_H_same": float(e["H"].mean()),
        "gain_on_switched": float(gain[sw].mean()) if k else None,
        "gain_by_choice": {
            c: [float(np.nanmean(gain[chosen == c])), int((chosen == c).sum())] for c in labs
        },
        "funnel": fc,
    }



def _leg_delta(price: float, fwd: float, k: float, t: float, right: str) -> float:
    """Black-Scholes delta of one long option at its own mid IV on the forward, zero carry."""
    from scipy.stats import norm

    from earnings_iv_crush.research.hedged_hold import option_iv

    iv = option_iv(price, fwd, k, t, right)
    if not np.isfinite(iv) or t <= 0:
        return float("nan")
    sd = iv * np.sqrt(t)
    d1 = (np.log(fwd / k) + 0.5 * sd * sd) / sd
    return float(norm.cdf(d1)) if right == "C" else float(norm.cdf(d1) - 1.0)


def _leg_vega(price: float, fwd: float, k: float, t: float, right: str) -> float:
    from scipy.stats import norm

    from earnings_iv_crush.research.hedged_hold import option_iv

    iv = option_iv(price, fwd, k, t, right)
    if not np.isfinite(iv) or t <= 0:
        return float("nan")
    sd = iv * np.sqrt(t)
    d1 = (np.log(fwd / k) + 0.5 * sd * sd) / sd
    return float(fwd * norm.pdf(d1) * np.sqrt(t))


def _pair_vega(e: pd.DataFrame, c: str, p: str) -> np.ndarray:
    return np.array([
        _leg_vega((cb + ca) / 2, f, kc, t, "C") + _leg_vega((pb + pa) / 2, f, kp, t, "P")
        for cb, ca, kc, pb, pa, kp, f, t in zip(
            e[f"{c}_bid"], e[f"{c}_ask"], e[f"{c}_k"], e[f"{p}_bid"], e[f"{p}_ask"], e[f"{p}_k"],
            e["fwd"], e["t0"])
    ])


def _h_vega(e: pd.DataFrame) -> np.ndarray:
    from earnings_iv_crush.research.hedged_hold import straddle_vega

    return np.array([
        straddle_vega(f, k, t, s) * 100.0 if np.isfinite(s) else np.nan  # per unit of vol
        for f, k, t, s in zip(e["fwd"], e["k0"], e["t0"], e["k0_mid_iv"])
    ])


def vega_matched(d: pd.DataFrame, which: str) -> dict:
    """1821-1823: strangles scaled to equal entry vega, base m0, net at the touch."""
    w = pd.read_parquet(HERE / "wings.parquet")
    w["entry_date"] = pd.to_datetime(w["entry_date"])
    e = d.merge(w, on=["ticker", "entry_date"], how="left", suffixes=("", "_w"))
    e["fwd"], e["t0"] = e["fwd"].astype(float), e["t0"].astype(float)
    vh = _h_vega(e)
    if which == "tight_wings":
        elig = e["wstatus"].eq("ok") & e["tw_status"].eq("ok") & e["g050_status"].eq("ok")
    elif which == "im2":
        elig = e["wstatus"].eq("ok") & e["g050_status"].eq("ok")
    else:
        elig = e["g100_status"].eq("ok") & e["oc_k"].notna()
    fc = funnel_check(e, elig, which)
    e = e[elig].copy()
    vh = vh[elig.to_numpy()]
    vb = _pair_vega(e, "bc", "bp") if which != "im1" else _pair_vega(e, "oc", "op")
    if which == "tight_wings":
        vt = _pair_vega(e, "tc", "tp")
        x = e["tw_usd"].to_numpy() * vb / vt / e["m0"].to_numpy()
        base = e["g050_usd"].to_numpy() / e["m0"].to_numpy()
        diff = pd.Series(x - base, index=e.index)
        lvl = pd.Series(e["tw_usd"].to_numpy() * vh / vt / e["m0"].to_numpy(), index=e.index)
        extra = {"switched_share": float(((e["tc_k"] != e["bc_k"]) | (e["tp_k"] != e["bp_k"])).mean()),
                 "vs_H_vega_matched": ci(lvl - e["H"], e["exit_date"])}
    else:
        usd = e["g050_usd"] if which == "im2" else e["g100_usd"]
        lvl = pd.Series(usd.to_numpy() * vh / vb / e["m0"].to_numpy(), index=e.index)
        diff = lvl - e["H"]
        mid = e["g050_usd_mid"] if which == "im2" else e["g100_usd_mid"]
        lvl_mid = mid.to_numpy() * vh / vb / e["m0"].to_numpy()
        extra = {"vega_scale_median": float(np.nanmedian(vh / vb)),
                 "level_mid_vega_matched": float(np.nanmean(lvl_mid)),
                 "H_mid_same": float(e["H_mid"].mean())}
    ok = np.isfinite(diff.to_numpy()) & np.isfinite(lvl.to_numpy())
    print(f"  vega finite: {int(ok.sum())} of {len(e)}")
    return {
        "res": ci(diff[ok], e.loc[ok, "exit_date"]),
        "null_pct": None,
        "level_chosen": ci(lvl[ok], e.loc[ok, "exit_date"]),
        "level_H_same": float(e.loc[ok, "H"].mean()),
        **extra,
        "funnel": fc,
    }

def _tight_vs_h(d: pd.DataFrame) -> dict:
    """1826 (frozen): the vol-tight IM/2 strangle scaled to H's entry vega, minus H."""
    r = vega_matched(d, "tight_wings")
    r["res_vs_base_strangle"] = r["res"]
    r["res"] = r.pop("vs_H_vega_matched")
    return r


def cheaper_vega(d: pd.DataFrame) -> dict:
    """1824: per event, the ATM straddle or the vol-tight IM/2 strangle (vega-matched to H),
    whichever has the lower 15:59 entry half-spread per unit of vega; outcome vs H, base m0."""
    w = pd.read_parquet(HERE / "wings.parquet")
    w["entry_date"] = pd.to_datetime(w["entry_date"])
    e = d.merge(w, on=["ticker", "entry_date"], how="left", suffixes=("", "_w"))
    elig = e["wstatus"].eq("ok") & e["tw_status"].eq("ok")
    fc = funnel_check(e, elig, "cheaper_vega")
    e = e[elig].copy()
    vh, vt = _h_vega(e), _pair_vega(e, "tc", "tp")
    s_vm = e["tw_usd"].to_numpy() * vh / vt / e["m0"].to_numpy()
    c_h = ((e["k0_ask"] - e["k0_bid"]) / 2).to_numpy() / vh
    c_s = ((e["tc_ask"] - e["tc_bid"] + e["tp_ask"] - e["tp_bid"]) / 2).to_numpy() / vt
    pick_s = c_s < c_h
    out = np.where(pick_s, s_vm, e["H"].to_numpy())
    gain = pd.Series(out - e["H"].to_numpy(), index=e.index)
    always = pd.Series(s_vm - e["H"].to_numpy(), index=e.index)
    # null: the same number of events switched to the strangle at random
    nul = matched_random_null(always.to_numpy(), pick_s, lambda x: float(np.nansum(x)) / len(e),
                              n_draws=N_DRAWS, seed=SEED)
    return {
        "res": ci(gain, e["exit_date"]),
        "null_pct": nul.percentile,
        "null_median": float(np.nanmedian(nul.null)),
        "share_strangle": float(pick_s.mean()),
        "always_strangle_vs_H": ci(always, e["exit_date"]),
        "level_chosen": ci(pd.Series(out, index=e.index), e["exit_date"]),
        "level_H_same": float(e["H"].mean()),
        "funnel": fc,
    }


def vol_spread_three(d: pd.DataFrame) -> dict:
    """1825: 1819 with the strike chosen on spread per unit of straddle vega (vol terms)."""
    from earnings_iv_crush.research.hedged_hold import straddle_vega

    d = add_entry_night_hedge(d.copy())
    for lab in ("k0", "km1", "kp1"):
        v = np.array([
            straddle_vega(f, k, t, s) if np.isfinite(k) and np.isfinite(s) else np.nan
            for f, k, t, s in zip(d["fwd"], d[f"{lab}_K"], d["t0"], d[f"{lab}_mid_iv"])
        ])
        d[f"{lab}_vspr"] = d[f"{lab}_spr"] / v
    return strike_rule(d, "three", "vspr", "min", gcol="gdn")


# ── structures and expiries ─────────────────────────────────────────────────


def strangle(d: pd.DataFrame, lab: str) -> dict:
    elig = d[f"{lab}_status"].eq("ok") & d["k0_ok"]
    fc = funnel_check(d, elig, lab)
    e = d[elig].copy()
    own = e[f"{lab}_usd"] / e[f"{lab}_mg"]
    per_m0 = e[f"{lab}_usd"] / e["m0"] - e["H"]
    mr = (e["abs_move"] / e["im"]).clip(upper=99)
    bins = pd.cut(mr, [0, 0.5, 1, 1.5, 2, np.inf])
    return {
        "res": ci(own - e["H"], e["exit_date"]),
        "per_contract_m0": ci(per_m0, e["exit_date"]),
        "null_pct": None,
        "level_chosen": ci(own, e["exit_date"]),
        "level_H_same": float(e["H"].mean()),
        "level_mid_own": float((e[f"{lab}_usd_mid"] / e[f"{lab}_mg"]).mean()),
        "premium_ratio": float((e[f"{lab}_sale"] / e["s0"]).median()),
        "half_spread_frac_med": float(
            ((e[f"{lab}_mid_sale"] - e[f"{lab}_sale"]) / e[f"{lab}_mid_sale"]).median()
        ),
        "H_half_spread_frac_med": float(((e["mid0"] - e["s0"]) / e["mid0"]).median()),
        "diff_by_move_ratio": {
            str(k): [round(float(v.mean()), 5), int(len(v))]
            for k, v in (own - e["H"]).groupby(bins, observed=True)
        },
        "funnel": fc,
    }


def monthly(d: pd.DataFrame) -> dict:
    elig = d["mon_status"].eq("ok") & d["k0_ok"] & (pd.to_datetime(d["mon_expiry"]) != d["expiry"])
    fc = funnel_check(d, elig, "monthly")
    e = d[elig].copy()
    m_mon = MARGIN_SPOT_FRAC * e["fwd"] + e["mon_bid"]  # front forward; carry gap ignored
    own = e["mon_usd"] / m_mon
    days = e["mon_days"]
    return {
        "res": ci(own - e["H"], e["exit_date"]),
        "per_contract_m0": ci(e["mon_usd"] / e["m0"] - e["H"], e["exit_date"]),
        "null_pct": None,
        "level_chosen": ci(own, e["exit_date"]),
        "level_H_same": float(e["H"].mean()),
        "level_mid_own": float((e["mon_usd_mid"] / m_mon).mean()),
        "H_mid_same": float(e["H_mid"].mean()),
        "half_spread_frac_med_mon": float(((e["mon_mid"] - e["mon_bid"]) / e["mon_mid"]).median()),
        "half_spread_frac_med_H": float(((e["mid0"] - e["s0"]) / e["mid0"]).median()),
        "entry_half_spread_own_mon": float(((e["mon_mid"] - e["mon_bid"]) / m_mon).mean()),
        "entry_half_spread_m0_H": float(((e["mid0"] - e["s0"]) / e["m0"]).mean()),
        "median_days_mon": float(days.median()),
        "funnel": fc,
    }


TRIALS_DEF = {
    1811: ("R1 tight-of-bracket strike", lambda d: strike_rule(d, "bracket", "spr", "min"),
           "base m0, per trade, net at touch, paired gain over H"),
    1812: ("R2 tight-of-three strike", lambda d: strike_rule(d, "three", "spr", "min"),
           "base m0, per trade, net at touch, paired gain over H"),
    1813: ("Control: always the bracketing neighbour", always_neighbour,
           "base m0, per trade, net at touch, paired gain over H"),
    1814: ("R3 richest bid-IV of three", lambda d: strike_rule(d, "three", "bid_iv", "max"),
           "base m0, per trade, net at touch, paired gain over H"),
    1815: ("Strangle at IM/2, hedged hold", lambda d: strangle(d, "g050"),
           "own margin vs m0 (margin-matched), per trade, net at touch, paired"),
    1816: ("Strangle at 1 IM, hedged hold (1,557 construction)", lambda d: strangle(d, "g100"),
           "own margin vs m0 (margin-matched), per trade, net at touch, paired"),
    1817: ("Standard monthly expiry ATM, hedged hold", monthly,
           "own margin vs m0 (margin-matched), per trade, net at touch, paired"),
    1818: ("R4 per-leg tightest quote on bracketing strikes", legs_rule,
           "base m0, per trade, net at touch, paired gain over build_g ATM straddle"),
    1819: ("R2 tight-of-three, entry-night delta-matched",
           lambda d: strike_rule(add_entry_night_hedge(d.copy()), "three", "spr", "min",
                                 gcol="gdn"),
           "base m0, per trade, net at touch incl. stock hedge cost, paired gain over H"),
    1820: ("R4 per-leg tightest, entry-night delta-matched",
           lambda d: legs_rule(add_entry_night_hedge(d.copy()), dm=True),
           "base m0, per trade, net at touch incl. stock hedge cost, paired over build_g ATM"),
    1821: ("IM/2 strangle, wings tightest in vol terms", lambda d: vega_matched(d, "tight_wings"),
           "base m0, vega-matched to the IM/2 strangle, per trade, net at touch, paired"),
    1822: ("IM/2 strangle vs H, vega-matched", lambda d: vega_matched(d, "im2"),
           "base m0, strangle scaled to H entry vega, per trade, net at touch, paired"),
    1823: ("1-IM strangle vs H, vega-matched", lambda d: vega_matched(d, "im1"),
           "base m0, strangle scaled to H entry vega, per trade, net at touch, paired"),
    1824: ("Per event: straddle or vol-tight IM/2 strangle, lower half-spread per vega",
           cheaper_vega, "base m0, vega-matched to H, per trade, net at touch, paired vs H"),
    1825: ("Tight-of-three straddle strike on spread per vega, delta-matched", vol_spread_three,
           "base m0, per trade, net at touch incl. stock hedge cost, paired gain over H"),
    1826: ("FROZEN: vol-tight IM/2 strangle, vega-matched to H, vs H", _tight_vs_h,
           "base m0, strangle scaled to H entry vega, per trade, net at touch, paired vs H"),
}


def logged() -> set[tuple[str, str]]:
    if not TRIALS.exists():
        return set()
    with TRIALS.open(encoding="utf-8") as fh:
        return {(r["trial_id"], r["block"]) for r in csv.DictReader(fh)}


def append(row: dict) -> None:
    new = not TRIALS.exists()
    with TRIALS.open("a", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=COLS)
        if new:
            w.writeheader()
        w.writerow(row)


def verdict(r: dict, pct: float | None) -> str:
    lo, hi, t = r["low"], r["high"], r["t"]
    if lo > 0 and (pct is None or pct >= 95):
        return "gain (interval above zero)" + ("" if pct is None else f", null pct {pct:.1f}")
    if hi < 0:
        return "loss (interval below zero)"
    return "no difference (interval spans zero)"


def main() -> None:
    blk = sys.argv[1]
    ids = [int(x) for x in sys.argv[2:]]
    mech = json.loads((HERE / "mechanisms.json").read_text(encoding="utf-8"))
    y0, y1 = BLOCKS[blk]
    d = load()
    d = d[d["year"].between(y0, y1) & d["status_b"].eq("ok")]
    print(f"block {blk} ({y0}-{y1}): {len(d)} events with status ok")
    done = logged()
    allres = {}
    for tid in ids:
        name, fn, basis = TRIALS_DEF[tid]
        out = fn(d)
        allres[tid] = out
        r = out["res"]
        pct = out.get("null_pct")
        v = verdict(r, pct)
        print(f"\n{tid} {name} [{blk}]: {r['point']:+.5f} [{r['low']:+.5f}, {r['high']:+.5f}] "
              f"N={r['n']} t={r['t']:.2f} null={pct}  -> {v}")
        print(json.dumps({k: v for k, v in out.items() if k not in ("res",)}, indent=1,
                         default=str))
        key = (str(tid), f"{y0}-{y1}")
        if key in done or os.environ.get("LANEB_ARMS"):
            print("  (already logged; not rewritten)")
            continue
        append(
            {
                "trial_id": tid,
                "hypothesis": name,
                "mechanism": mech[str(tid)],
                "block": f"{y0}-{y1}",
                "N": r["n"],
                "effect": f"{r['point']:.6f}",
                "ci_low": f"{r['low']:.6f}",
                "ci_high": f"{r['high']:.6f}",
                "t": f"{r['t']:.2f}",
                "null_percentile": "" if pct is None else f"{pct:.1f}",
                "basis": basis + "; level of chosen book "
                + f"{out['level_chosen']['point']:+.5f} [{out['level_chosen']['low']:+.5f}, "
                + f"{out['level_chosen']['high']:+.5f}]",
                "verdict": v,
            }
        )
    res_path = HERE / f"results_{blk}_{'_'.join(map(str, ids))}.json"
    if not os.environ.get("LANEB_ARMS"):
        res_path.write_text(json.dumps(allres, indent=1, default=str), encoding="utf-8")
        print("wrote", res_path)


if __name__ == "__main__":
    main()
