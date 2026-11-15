"""
lib.py
Lane J (name-level persistence of residual value), alpha hunt 2, 2026-11-13.

Loader, persistence measurement with a within-year name-shuffle null, causal empirical-Bayes
name effects, a within-cell selector scorer with a date-clustered bootstrap and a cell-matched
(implied-move tercile x tenor) random null, and the trial log.

Outcome basis
-------------
``H`` and ``B`` are the hedged hold to expiry and the next-session buy-back, net at the touch,
per trade, on margin m0 = 0.20 x forward + 15:59 bid premium (built by
`research/timing/2026-11-02-hedged-event-hold`). ``y = H m0 / mid0`` and ``yb = B m0 / mid0``
are the same P&L per unit of premium at the entry mid (size neutral). Residual value is ``y``
less its mean within the causal implied-move tercile x tenor cell, so every residual is tenor
matched. ``y_mid`` uses ``H_mid`` (both legs at the mid, hedge costs included as built).

Point in time
-------------
A name's track record at an event uses only events whose outcome had resolved strictly before
the entry session: expiry for the hold, the exit session for the buy-back. Cell means, the
winsorisation cut-offs and the empirical-Bayes hyperparameters are re-estimated at each entry
date from those resolved events only. Every feature is stamped as of the entry session, 15:59.

Usage
-----
    import lib; d = lib.load(); sig = lib.causal_name_effect(d, "y", "expiry")
"""

from __future__ import annotations

import csv
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
sys.path.insert(0, str(ROOT))

from earnings_iv_crush.research.protocol import (  # noqa: E402
    date_clustered_ci,
    matched_random_null,
)

FEATURES = ROOT / "outputs/research/2026-11-13-alpha-hunt/lane5-niche/features.parquet"
TRIALS = HERE / "trials.csv"
BLOCKS = {
    "discovery": (2013, 2018),
    "heldout": (2019, 2024),
    "viewed_2025_26": (2025, 2026),  # '*' row in research/ledger/blocks.csv: exploratory only
}
N_BOOT = 5000
SEED = 0
MIN_SIDE = 2  # events per side for a cell to contribute (as the round-1 scorers)
MIN_PRIOR_SIGNALS = 200  # causal quantile cuts need this many earlier signal values
WINSOR_Q = (0.01, 0.99)  # residual tails: y reaches -13 premiums on a handful of events
MIN_CELL_KNOWN = 20  # resolved events in a cell before its mean is used
MIN_GROUP_KNOWN = 30  # resolved events in an industry group before it is a shrinkage target
TENOR_LABELS = ["0-1d", "2-4d", "5-9d", "10d+"]
FIELDS = [
    "trial_id", "hypothesis", "mechanism", "block", "N", "n_treated", "n_names", "effect",
    "ci_low", "ci_high", "t", "null_pct", "basis", "treated_level", "level_ci_low",
    "level_ci_high", "pool_level", "effect_ex_top5", "verdict", "label",
]


# ── data ─────────────────────────────────────────────────────────────────────


def load() -> pd.DataFrame:
    """The 9,350 scorable hedged-hold events with outcomes, controls and causal cells."""
    d = pd.read_parquet(FEATURES)
    n0 = len(d)
    for c in ("entry_date", "exit_date", "expiry", "announce_date"):
        d[c] = pd.to_datetime(d[c]).dt.normalize()
    d["year"] = d["announce_date"].dt.year
    d["y_mid"] = d["H_mid"] * d["m0"] / d["mid0"]
    ok_mid = np.isfinite(d["exit_mid"]) & (d["exit_mid"] >= 0)
    d["yb_mid"] = np.where(ok_mid, 1.0 - d["exit_mid"] / d["mid0"], np.nan)
    d["log_im"] = np.log(d["implied_move"])
    d["tenor_code"] = pd.Categorical(d["tenor"], TENOR_LABELS).codes
    d = d.sort_values(["entry_date", "ticker"]).reset_index(drop=True)
    print(
        f"[load] {n0} events, {d['ticker'].nunique()} names; causal cell assigned "
        f"{int((d['im_bin'] >= 0).sum())}; two-sided exit mid {int(ok_mid.sum())} "
        f"(yb_mid defined); industry group known {int(d['igroup'].notna().sum())}"
    )
    return d


# ── persistence measurement ──────────────────────────────────────────────────


def within_block_residual(
    d: pd.DataFrame, col: str, controls: list[str] | None = None
) -> pd.Series:
    """Descriptive residual: ``col`` less its cell x year mean, optionally less an OLS fit.

    Cell x year demeaning removes the tenor and implied-move tercile mix and every common
    year shock. With ``controls``, a pooled OLS of the demeaned outcome on the demeaned
    controls is removed as well (fitted on the block itself, so this is descriptive only).
    """
    x = d[[col, "cell", "year"] + (controls or [])].copy()
    x[col] = x[col].clip(*x[col].quantile(list(WINSOR_Q)).to_numpy())
    g = x.groupby(["cell", "year"])
    r = x[col] - g[col].transform("mean")
    if controls:
        xc = x[controls] - g[controls].transform("mean")
        ok = np.isfinite(xc).all(axis=1) & np.isfinite(r)
        beta, *_ = np.linalg.lstsq(xc[ok].to_numpy(float), r[ok].to_numpy(float), rcond=None)
        r = (r - xc.to_numpy(float) @ beta).where(ok)
        print(f"    [controls] {controls} beta {np.round(beta, 4).tolist()}, N {int(ok.sum())}")
    return r


def year_pair_persistence(
    d: pd.DataFrame, resid: pd.Series, years: tuple[int, int], n_perm: int = N_BOOT
) -> dict:
    """Cross-name correlation of a name's mean residual in year t with year t+1.

    Pooled over consecutive year pairs inside ``years`` by a names-weighted Fisher z. The null
    shuffles names within year t+1 for each pair, which keeps each year's cross-section and
    breaks only the name link. The interval resamples names (whole name histories).
    """
    x = d.assign(_r=resid)[["ticker", "year", "_r"]].dropna()
    x = x[x["year"].between(*years)]
    m = x.groupby(["ticker", "year"])["_r"].mean().unstack()
    pairs = []
    for t in range(years[0], years[1]):
        if t in m.columns and t + 1 in m.columns:
            p = m[[t, t + 1]].dropna()
            if len(p) >= 20:
                pairs.append((t, p.index.to_numpy(), p[t].to_numpy(), p[t + 1].to_numpy()))
    if not pairs:
        raise ValueError("no year pair with 20 or more names in common")

    def pooled(arrs: list[tuple[np.ndarray, np.ndarray]]) -> float:
        z = [np.arctanh(np.clip(np.corrcoef(a, b)[0, 1], -0.999, 0.999)) for a, b in arrs]
        w = [len(a) - 3 for a, _ in arrs]
        return float(np.tanh(np.average(z, weights=w)))

    obs = pooled([(a, b) for _, _, a, b in pairs])
    spear = pooled(
        [(pd.Series(a).rank().to_numpy(), pd.Series(b).rank().to_numpy()) for _, _, a, b in pairs]
    )
    rng = np.random.default_rng(SEED)
    null = np.array(
        [pooled([(a, rng.permutation(b)) for _, _, a, b in pairs]) for _ in range(n_perm)]
    )
    names = np.unique(np.concatenate([n for _, n, _, _ in pairs]))
    boots = []
    for _ in range(n_perm // 5):
        pick = rng.choice(names, names.size, replace=True)
        cnt = pd.Series(pick).value_counts()
        arrs = []
        for _, n, a, b in pairs:
            rep = cnt.reindex(n).fillna(0).to_numpy(int)
            if rep.sum() >= 20:
                arrs.append((np.repeat(a, rep), np.repeat(b, rep)))
        boots.append(pooled(arrs))
    boots = np.asarray(boots)
    per_pair = {int(t): round(float(np.corrcoef(a, b)[0, 1]), 3) for t, _, a, b in pairs}
    return {
        "r": obs,
        "spearman": spear,
        "null_pct": float(100 * (null < obs).mean()),
        "null_sd": float(null.std()),
        "ci": (float(np.percentile(boots, 2.5)), float(np.percentile(boots, 97.5))),
        "t": float(obs / null.std()),
        "n_pairs": int(sum(len(a) for _, _, a, _ in pairs)),
        "n_names": int(names.size),
        "per_pair": per_pair,
    }


def icc(d: pd.DataFrame, resid: pd.Series, years: tuple[int, int], n_perm: int = 1000) -> dict:
    """Share of residual variance that is a fixed name effect, with a within-year shuffle null.

    Method of moments: tau2 = var(name means) - mean(sigma2 / n_i). The null shuffles ticker
    labels within each year, which keeps year composition and destroys the name link.
    """
    x = d.assign(_r=resid)[["ticker", "year", "_r"]].dropna()
    x = x[x["year"].between(*years)].reset_index(drop=True)

    def stat(tk: np.ndarray) -> tuple[float, float]:
        g = pd.DataFrame({"t": tk, "r": x["_r"].to_numpy()}).groupby("t")["r"]
        n, mu, var = g.size(), g.mean(), g.var(ddof=1)
        keep = n >= 2
        s2 = float(((n[keep] - 1) * var[keep]).sum() / (n[keep] - 1).sum())
        tau2 = float(mu[keep].var(ddof=1) - (s2 / n[keep]).mean())
        return tau2, s2

    tau2, s2 = stat(x["ticker"].to_numpy())
    rng = np.random.default_rng(SEED)
    tk = x["ticker"].to_numpy().copy()
    yrs = x["year"].to_numpy()
    null = []
    for _ in range(n_perm):
        sh = tk.copy()
        for y in np.unique(yrs):
            ix = np.flatnonzero(yrs == y)
            sh[ix] = rng.permutation(sh[ix])
        null.append(stat(sh)[0])
    null = np.asarray(null)
    return {
        "tau2": tau2,
        "sigma2": s2,
        "icc": tau2 / (tau2 + s2) if tau2 > 0 else 0.0,
        "null_pct": float(100 * (null < tau2).mean()),
        "tau2_null_median": float(np.median(null)),
        "tau_sd_units": float(np.sqrt(max(tau2, 0.0))),
    }


# ── causal name effect ───────────────────────────────────────────────────────


def causal_name_effect(
    d: pd.DataFrame,
    col: str,
    resolve_col: str,
    *,
    shrink_to: str = "zero",
    controls: list[str] | None = None,
    winsor: bool = True,
) -> pd.DataFrame:
    """Empirical-Bayes name effect on cell-residual ``col`` from strictly resolved events.

    At each entry date t the known set is every event with ``resolve_col`` < t. On it: cell
    means (cells with at least MIN_CELL_KNOWN events), residuals, optional OLS on demeaned
    controls, causal winsorisation, then per name the mean residual and count. Hyperparameters
    by method of moments: sigma2 the pooled within-name variance, tau2 the excess variance of
    name means. The shrunken effect is m + B (mean - m) with B = tau2 / (tau2 + sigma2 / n),
    m = 0 or the industry-group mean of known residuals.

    Returns columns n_prior, raw, shrunk, tau2, sigma2, B on ``d``'s index.
    """
    out = pd.DataFrame(
        np.nan, index=d.index, columns=["n_prior", "raw", "shrunk", "tau2", "sigma2", "B"]
    )
    res_t = d[resolve_col].to_numpy("datetime64[ns]")
    y_all = d[col].to_numpy(float)
    cell = d["cell"].to_numpy(float)
    tick = d["ticker"].to_numpy()
    grp = d["igroup"].to_numpy(object)
    X = d[controls].to_numpy(float) if controls else None
    tau_zero = 0
    for t, idx in d.groupby("entry_date").indices.items():
        known = (res_t < np.datetime64(t)) & np.isfinite(y_all) & (cell >= 0)
        if known.sum() < MIN_PRIOR_SIGNALS:
            continue
        k = np.flatnonzero(known)
        yk, ck = y_all[k], cell[k]
        cs = pd.Series(yk).groupby(ck)
        cmean, ccount = cs.transform("mean").to_numpy(), cs.transform("size").to_numpy()
        r = np.where(ccount >= MIN_CELL_KNOWN, yk - cmean, np.nan)
        if X is not None:
            xk = X[k]
            xd = xk - pd.DataFrame(xk).groupby(ck).transform("mean").to_numpy()
            ok = np.isfinite(xd).all(axis=1) & np.isfinite(r)
            if ok.sum() > 50:
                beta, *_ = np.linalg.lstsq(xd[ok], r[ok], rcond=None)
                r = np.where(ok, r - xd @ beta, np.nan)
        if winsor:
            lo, hi = np.nanquantile(r, WINSOR_Q)
            r = np.clip(r, lo, hi)
        df = pd.DataFrame({"t": tick[k], "g": grp[k], "r": r}).dropna(subset=["r"])
        g = df.groupby("t")["r"]
        n, mu, var = g.size(), g.mean(), g.var(ddof=1)
        two = n >= 2
        if two.sum() < 10:
            continue
        s2 = float(((n[two] - 1) * var[two]).sum() / (n[two] - 1).sum())
        tau2 = max(0.0, float(mu.var(ddof=1) - (s2 / n).mean()))
        tau_zero += tau2 == 0.0
        if shrink_to == "igroup":
            gg = df.dropna(subset=["g"]).groupby("g")["r"]
            gmean = gg.mean()[gg.size() >= MIN_GROUP_KNOWN]
        for i in idx:
            name = tick[i]
            if name not in n.index:
                continue
            ni, mi = int(n[name]), float(mu[name])
            target = 0.0
            if shrink_to == "igroup" and isinstance(grp[i], str) and grp[i] in gmean.index:
                target = float(gmean[grp[i]])
            b = tau2 / (tau2 + s2 / ni) if tau2 > 0 else 0.0
            out.loc[d.index[i]] = [ni, mi, target + b * (mi - target), tau2, s2, b]
    if tau_zero:
        print(f"    [warn] tau2 floored at zero on {tau_zero} entry dates: no name effect there")
    print(
        f"    [signal {col}/{resolve_col}/{shrink_to}{'/ctrl' if controls else ''}] defined "
        f"{int(out['shrunk'].notna().sum())} of {len(d)}; median n_prior "
        f"{out['n_prior'].median():.0f}; median shrinkage B {out['B'].median():.3f}"
    )
    return out


def causal_quantile_bins(
    v: np.ndarray, dates: pd.Series, n_bins: int, min_prior: int = MIN_PRIOR_SIGNALS
) -> np.ndarray:
    """Bin 0..n_bins-1 from quantiles of strictly earlier dates' values; -1 if unassigned."""
    v = np.asarray(v, float)
    dd = pd.to_datetime(dates).dt.normalize().to_numpy()
    out = np.full(v.size, -1, int)
    order = np.argsort(dd, kind="stable")
    qs = np.linspace(0, 1, n_bins + 1)[1:-1]
    seen: list[float] = []
    i = 0
    while i < order.size:
        j = i
        while j < order.size and dd[order[j]] == dd[order[i]]:
            j += 1
        idx = order[i:j]
        if len(seen) >= min_prior:
            cuts = np.quantile(np.asarray(seen), qs)
            for k in idx:
                if np.isfinite(v[k]):
                    out[k] = int(np.searchsorted(cuts, v[k], side="right"))
        seen.extend(float(x) for x in v[idx] if np.isfinite(x))
        i = j
    return out


# ── selector scoring ─────────────────────────────────────────────────────────


def _delta(y: np.ndarray, f: np.ndarray, c: np.ndarray) -> float:
    num = den = 0.0
    for u in np.unique(c):
        m = c == u
        k = int((f & m).sum())
        if k >= MIN_SIDE and int((~f & m).sum()) >= MIN_SIDE:
            num += k * (y[f & m].mean() - y[~f & m].mean())
            den += k
    return num / den if den else float("nan")


def _boot_delta(y: np.ndarray, f: np.ndarray, c: np.ndarray, keys: np.ndarray) -> np.ndarray:
    """Date-clustered bootstrap of the within-cell contrast, vectorised by cluster weights."""
    rng = np.random.default_rng(SEED)
    uk, inv = np.unique(keys, return_inverse=True)
    cells = np.unique(c)
    FT = np.column_stack([(f & (c == u)).astype(float) for u in cells])
    FU = np.column_stack([(~f & (c == u)).astype(float) for u in cells])
    YT, YU = FT * y[:, None], FU * y[:, None]
    out = []
    for _ in range(N_BOOT // 500):
        cnt = np.stack([np.bincount(rng.integers(0, uk.size, uk.size), minlength=uk.size)
                        for _ in range(500)]).astype(float)
        W = cnt[:, inv]
        kt, ku, st, su = W @ FT, W @ FU, W @ YT, W @ YU
        use = (kt >= MIN_SIDE) & (ku >= MIN_SIDE)
        with np.errstate(invalid="ignore", divide="ignore"):
            diff = np.where(use, st / np.where(use, kt, 1) - su / np.where(use, ku, 1), 0.0)
        num = (np.where(use, kt, 0) * diff).sum(1)
        den = np.where(use, kt, 0).sum(1)
        out.append(np.where(den > 0, num / np.where(den > 0, den, 1), np.nan))
    return np.concatenate(out)


def _cell_null(y: np.ndarray, f: np.ndarray, c: np.ndarray) -> float:
    """Percentile of the treated mean among same-count-per-cell random draws (tenor matched)."""
    rng = np.random.default_rng(SEED)
    tot = np.zeros(N_BOOT)
    k_all = 0
    for u in np.unique(c):
        g = np.flatnonzero(c == u)
        k = int(f[g].sum())
        if k == 0:
            continue
        k_all += k
        if k == g.size:
            tot += y[g].sum()
            continue
        key = rng.random((N_BOOT, g.size))
        pick = np.argpartition(key, k - 1, axis=1)[:, :k]
        tot += y[g][pick].sum(1)
    return float(100 * (tot / k_all < y[f].mean()).mean())


def score(
    d: pd.DataFrame,
    flag: pd.Series,
    defined: pd.Series,
    block: str,
    *,
    hyp: str,
    ycol: str = "y",
    level_col: str = "H",
    cellcol: str = "cell",
    quiet: bool = False,
) -> dict:
    """Within-cell treated minus untreated on ``ycol``; levels on ``level_col``; name carriage."""
    if block not in BLOCKS:
        raise ValueError(block)
    if block == "heldout" and not (HERE / f"freeze_{hyp}.md").exists():
        raise PermissionError(f"held-out refused: no freeze_{hyp}.md")
    lo, hi = BLOCKS[block]
    ok = (
        defined.to_numpy(bool)
        & (d["im_bin"] >= 0).to_numpy()
        & d["year"].between(lo, hi).to_numpy()
        & np.isfinite(d[ycol]).to_numpy()
    )
    b = d[ok]
    f = flag.to_numpy(bool)[ok]
    if f.sum() < 20 or (~f).sum() < 20:
        raise ValueError(f"{hyp} {block}: {int(f.sum())} treated of {len(b)}: too few")
    y, c = b[ycol].to_numpy(float), b[cellcol].to_numpy(float)
    keys = b["announce_date"].to_numpy()
    eff = _delta(y, f, c)
    draws = _boot_delta(y, f, c, keys)
    lo_ci, hi_ci = np.nanpercentile(draws, [2.5, 97.5])
    se = float(np.nanstd(draws, ddof=1))
    lvl = date_clustered_ci(b.loc[f, level_col], b.loc[f, "announce_date"], np.mean)
    pool = float(b[level_col].mean())
    unmatched = matched_random_null(y, f, np.mean).percentile
    # name carriage: contribution of each treated name to the contrast
    um = pd.Series(y[~f]).groupby(c[~f]).mean()
    contrib = pd.Series(y[f] - pd.Series(c[f]).map(um).to_numpy(), index=b.index[f])
    by_name = contrib.groupby(b.loc[f, "ticker"]).sum().sort_values(ascending=False)
    top5 = by_name.index[:5]
    keep = ~b["ticker"].isin(top5).to_numpy()
    eff_ex5 = _delta(y[keep], f[keep], c[keep])
    res = {
        "hyp": hyp, "block": f"{block} {lo}-{hi}", "N": int(len(b)), "n_treated": int(f.sum()),
        "n_names": int(b.loc[f, "ticker"].nunique()), "effect": eff, "ci_low": float(lo_ci),
        "ci_high": float(hi_ci), "t": eff / se if se > 0 else np.nan,
        "null_pct": _cell_null(y, f, c), "null_pct_unmatched": unmatched,
        "treated_level": lvl.point, "level_ci_low": lvl.low, "level_ci_high": lvl.high,
        "pool_level": pool, "effect_ex_top5": eff_ex5,
        "top5": ", ".join(f"{k} {v:+.2f}" for k, v in by_name.iloc[:5].items()),
        "top_name_share": float(b.loc[f, "ticker"].value_counts(normalize=True).iloc[0]),
    }
    if not quiet:
        print(
            f"  {hyp} [{res['block']}] N {res['N']}, treated {res['n_treated']} "
            f"({res['n_names']} names, largest {res['top_name_share']:.1%})\n"
            f"    Delta {ycol} within cell {eff:+.4f} [{lo_ci:+.4f}, {hi_ci:+.4f}] t "
            f"{res['t']:+.2f}; tenor-matched null pct {res['null_pct']:.1f} "
            f"(unmatched {unmatched:.1f}); ex top-5 names {eff_ex5:+.4f}\n"
            f"    level {level_col} on m0, net at touch, treated {lvl.point:+.4f} "
            f"[{lvl.low:+.4f}, {lvl.high:+.4f}] vs pool {pool:+.4f}\n"
            f"    top-5 contributing names (sum of per-event contrast): {res['top5']}"
        )
    return res


def log_trial(
    trial_id: int, res: dict, *, mechanism: str, basis: str, label: str, passed: bool | None = None
) -> None:
    """Append one scored variant to trials.csv. Pass rule: CI above zero and null pct >= 95."""
    if passed is None:
        passed = res["ci_low"] > 0 and res["null_pct"] >= 95
    nan = float("nan")
    row = {k: res.get(k, nan) for k in FIELDS}
    row.update(
        trial_id=trial_id, hypothesis=res["hyp"], mechanism=mechanism, basis=basis,
        verdict="pass" if passed else "fail", label=label,
    )
    for k in ("effect", "ci_low", "ci_high", "treated_level", "level_ci_low", "level_ci_high",
              "pool_level", "effect_ex_top5"):
        if isinstance(row[k], float):
            row[k] = round(row[k], 5)
    for k in ("t", "null_pct"):
        if isinstance(row[k], float):
            row[k] = round(row[k], 2)
    new = not TRIALS.exists()
    with TRIALS.open("a", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=FIELDS)
        if new:
            w.writeheader()
        w.writerow(row)
    print(f"    -> trial {trial_id} {row['verdict'].upper()} ({label})")
