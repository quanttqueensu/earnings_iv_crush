"""
r2_components.py
Round 2, lane J, discovery 2013-18. Round 1 found no year-to-year persistence in residual value
(hold or buy-back, net or at the mid) while the entry spread and implied move are highly
persistent. Diagnosis: one event's residual carries the realised move, with a per-event sd of
about 0.54 premiums, so a name-year mean of two or three events cannot show a name effect
smaller than about 0.10 premiums. This round (a) lengthens the window to three-year halves,
(b) splits the buy-back residual into the noisy gap cost and the low-noise extrinsic value left
at exit, and the hold into the buy-back plus the post-reaction hedged leg H - B, and (c) builds
the pre-specified empirical-Bayes selectors, which also show what the causal shrinkage says.

Trials
  2057 split-half persistence, hold y        2058 split-half persistence, buy-back yb
  2059 split-half persistence, extrinsic at exit per premium (buy-back crush component)
  2060 split-half persistence, gap cost per premium (realised move component)
  2061 split-half persistence, post-reaction hedged leg (H - B) per premium
  2062 selector: EB name effect on yb, top quintile, shrink to zero, scored on yb
  2063 selector: EB name effect on y, top quintile, shrink to industry group, scored on y
  2064 selector: EB name effect on extrinsic, bottom quintile (least retained), scored on yb

Usage
-----
    python outputs/research/2026-11-13-alpha-hunt-2/laneJ-name-persistence/r2_components.py
"""

from __future__ import annotations

import numpy as np
import pandas as pd

import lib

L3 = lib.ROOT / "outputs/research/2026-11-13-alpha-hunt/lane3-surface-flow/all_features.parquet"
H1, H2 = (2013, 2015), (2016, 2018)


def attach(d: pd.DataFrame) -> pd.DataFrame:
    x = pd.read_parquet(L3, columns=["ticker", "entry_date", "gap_cost", "extrinsic",
                                     "jump_share", "fwd_exit"])
    x["entry_date"] = pd.to_datetime(x["entry_date"]).dt.normalize()
    d = d.merge(x, on=["ticker", "entry_date"], how="left", validate="one_to_one")
    d["hb"] = (d["H"] - d["B"]) * d["m0"] / d["mid0"]
    ok = d["extrinsic"].notna()
    print(
        f"[funnel] exit forward (gap/extrinsic split) present {int(ok.sum())} of {len(d)}; "
        f"mean yb covered {d.loc[ok, 'yb'].mean():+.4f} vs uncovered {d.loc[~ok, 'yb'].mean():+.4f}"
    )
    return d


def split_half(
    d: pd.DataFrame,
    resid: pd.Series,
    n_perm: int = lib.N_BOOT,
    h1: tuple[int, int] = H1,
    h2: tuple[int, int] = H2,
) -> dict:
    """Cross-name correlation of mean residual in half h1 with half h2; name-shuffle null."""
    x = d.assign(_r=resid).dropna(subset=["_r"])
    a = x[x.year.between(*h1)].groupby("ticker")["_r"].agg(["mean", "size"])
    b = x[x.year.between(*h2)].groupby("ticker")["_r"].agg(["mean", "size"])
    j = a.join(b, lsuffix="_a", rsuffix="_b", how="inner")
    j = j[(j["size_a"] >= 3) & (j["size_b"] >= 3)]
    r = float(np.corrcoef(j["mean_a"], j["mean_b"])[0, 1])
    rs = float(j["mean_a"].rank().corr(j["mean_b"].rank()))
    rng = np.random.default_rng(lib.SEED)
    va, vb = j["mean_a"].to_numpy(), j["mean_b"].to_numpy()
    null = np.array([np.corrcoef(va, rng.permutation(vb))[0, 1] for _ in range(n_perm)])
    boot = []
    for _ in range(n_perm):
        k = rng.integers(0, len(va), len(va))
        boot.append(np.corrcoef(va[k], vb[k])[0, 1])
    lo, hi = np.percentile(boot, [2.5, 97.5])
    # implied name sd: r = tau2 / (tau2 + s2 / n_bar), s2 from within-name variance
    s2 = float(x[x.year.between(h1[0], h2[1])].groupby("ticker")["_r"].var(ddof=1).mean())
    nbar = float(np.sqrt(j["size_a"] * j["size_b"]).mean())

    def tau(rr: float) -> float:
        return float(np.sqrt(max(rr, 0) * (s2 / nbar) / (1 - rr))) if rr < 1 else np.inf

    return {"r": r, "spearman": rs, "null_pct": float(100 * (null < r).mean()),
            "null_sd": float(null.std()), "ci": (float(lo), float(hi)), "n": len(j),
            "nbar": nbar, "tau_point": tau(r), "tau_upper": tau(float(hi))}


def run_split(d, tid, hyp, col, basis, mech, controls=None) -> None:
    print(f"\n== {hyp} ({col})")
    r = lib.within_block_residual(d, col, controls)
    p = split_half(d, r)
    print(
        f"  r {p['r']:+.4f} [{p['ci'][0]:+.4f}, {p['ci'][1]:+.4f}] Spearman {p['spearman']:+.4f}; "
        f"null pct {p['null_pct']:.1f}; names {p['n']} (>= 3 events per half, mean "
        f"{p['nbar']:.1f}); implied name sd {p['tau_point']:.4f}, upper {p['tau_upper']:.4f} "
        f"(units of {col})"
    )
    res = {"hyp": hyp, "block": "discovery 2013-15 vs 2016-18", "N": p["n"], "n_treated": "",
           "n_names": p["n"], "effect": p["r"], "ci_low": p["ci"][0], "ci_high": p["ci"][1],
           "t": p["r"] / p["null_sd"], "null_pct": p["null_pct"],
           "treated_level": p["tau_point"], "pool_level": p["tau_upper"]}
    lib.log_trial(tid, res, mechanism=mech, basis=basis + "; treated_level = implied name sd, "
                  "pool_level = its upper bound from the CI", label="descriptive")


def selector(d, tid, hyp, col, resolve, shrink, sign, ycol, level, mech, basis) -> pd.DataFrame:
    print(f"\n== {hyp}")
    s = lib.causal_name_effect(d, col, resolve, shrink_to=shrink)
    v = sign * s["shrunk"].to_numpy(float)
    if np.nanstd(v) == 0:
        raise ValueError(f"{hyp}: shrunken signal is constant (tau2 = 0 everywhere)")
    bins = lib.causal_quantile_bins(v, d["announce_date"], 5)
    flag = pd.Series(bins == 4, index=d.index)
    defined = pd.Series(bins >= 0, index=d.index)
    disc = d.year.between(*lib.BLOCKS["discovery"])
    print(f"  [funnel] defined {int((defined & disc).sum())} in discovery, treated "
          f"{int((flag & disc).sum())}; tau2 median {s.loc[disc, 'tau2'].median():.5f}, "
          f"B median {s.loc[disc, 'B'].median():.3f}")
    res = lib.score(d, flag, defined, "discovery", hyp=hyp, ycol=ycol, level_col=level)
    lib.log_trial(tid, res, mechanism=mech, basis=basis, label="exploratory")
    return s


def main() -> None:
    d = attach(lib.load())
    d = d[d["im_bin"] >= 0].reset_index(drop=True)
    sb = "Pearson r of name mean cell x year residual, 2013-15 vs 2016-18, names with >= 3 each; "
    m0 = ("a persistent name component in residual value, measured over three-year halves so "
          "that each mean averages about seven events")
    run_split(d, 2057, "J07 split-half persistence, hold net", "y",
              sb + "y = H per unit mid premium, net at touch", m0)
    run_split(d, 2058, "J08 split-half persistence, buy-back net", "yb",
              sb + "yb = B per unit mid premium, net at touch", m0)
    run_split(d, 2059, "J09 split-half persistence, extrinsic at exit", "extrinsic",
              sb + "extrinsic left in the held straddle at the exit mark per unit entry mid",
              "the post-event implied vol a name's options retain is a property of the name "
              "(investor base, dealer inventory); low-noise because it carries no realised move")
    run_split(d, 2060, "J10 split-half persistence, gap cost", "gap_cost",
              sb + "intrinsic at exit on the exit forward per unit entry mid",
              "own-history move size relative to the implied move (the noisy component)")
    run_split(d, 2061, "J11 split-half persistence, post-reaction hedged leg", "hb",
              sb + "(H - B) per unit mid premium, net at touch",
              "post-event variance premium of a name, captured by the hedged hold after the "
              "reaction, is a name property")
    b_y = ("within-cell (implied-move tercile x tenor) treated minus untreated, per trade, "
           "{o} per unit mid premium, net at touch; level {l} on m0 net at touch")
    selector(d, 2062, "J12 EB name effect on buy-back yb, top quintile, shrink to zero", "yb",
             "exit_date", "zero", 1, "yb", "B",
             "names whose buy-back residual value has been high keep it (dealer or clientele "
             "over-pricing); causal EB shrinkage stops thin histories being over-trusted",
             b_y.format(o="yb", l="B"))
    selector(d, 2063, "J13 EB name effect on hold y, top quintile, shrink to industry group", "y",
             "expiry", "igroup", 1, "y", "H",
             "as J12 on the hedged hold, shrunk towards the industry-group mean so a name with "
             "few events borrows its industry's record", b_y.format(o="y", l="H"))
    selector(d, 2064, "J14 EB name effect on extrinsic at exit, bottom quintile", "extrinsic",
             "exit_date", "zero", -1, "yb", "B",
             "names whose options keep the least extrinsic value after the print give the "
             "buy-back seller the most of the crush; a low-noise persistent component",
             b_y.format(o="yb", l="B"))


if __name__ == "__main__":
    main()
