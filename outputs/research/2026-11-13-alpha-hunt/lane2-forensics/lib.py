"""
lib.py
Scoring helpers for lane2-forensics: block-guarded ledger loading, the tenor-and-size-matched
random benchmark, date-clustered intervals and the trial log.

A rule is a boolean flag over events plus the sign the mechanism predicts for flagged minus
unflagged P&L. The primary statistic is Delta: the flagged-count-weighted mean, over cells of
tenor bucket by causal implied-move tercile, of mean P&L (net, at the touch, next-day buy-back,
per unit of entry premium) on flagged events minus unflagged events in the same cell. The book
mean is negative, so a Sharpe comparison would reward concentration; a difference in means
within cells answers "are flagged events better or worse than like-for-like events".
"""

from __future__ import annotations

import csv
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
LEDGER = HERE / "ledger_all.parquet"
TRIALS = HERE / "trials.csv"
FREEZE = HERE / "freeze_note.md"
N_BOOT = 2000
SEED = 0
Y = "pnl_prem"
SUBPERIODS = {"2013-17": (2013, 2017), "2018-21": (2018, 2021)}
TRIAL_FIELDS = [
    "trial_id", "round", "hypothesis", "mechanism", "predicted_sign", "block", "n_scored",
    "n_flagged", "delta_prem", "ci_low", "ci_high", "t", "null_pct", "delta_margin",
    "delta_2013_17", "delta_2018_21", "losers_flagged", "losers_total", "ordinary_flagged",
    "ratio_flagged", "ratio_unflagged", "im_flagged", "im_unflagged", "verdict",
]  # fmt: skip


def load(block: str = "discovery") -> pd.DataFrame:
    """Ledger rows for one block. The held-out block needs the freeze note to exist."""
    d = pd.read_parquet(LEDGER)
    if block == "heldout" and not FREEZE.exists():
        raise RuntimeError("held-out block requested before freeze_note.md exists")
    out = d[d["block"] == block].copy()
    print(f"funnel load {block}: {len(out)} of {len(d)} ledger rows")
    return out.reset_index(drop=True)


def _delta(y: np.ndarray, f: np.ndarray, c: np.ndarray) -> float:
    num = den = 0.0
    for u in np.unique(c):
        m = c == u
        k = int((f & m).sum())
        if k >= 2 and int((~f & m).sum()) >= 2:
            num += k * (y[f & m].mean() - y[~f & m].mean())
            den += k
    return num / den if den else float("nan")


def _boot(y: np.ndarray, f: np.ndarray, c: np.ndarray, dates: np.ndarray, n: int) -> np.ndarray:
    rng = np.random.default_rng(SEED)
    uniq, inv = np.unique(dates, return_inverse=True)
    order = np.argsort(inv, kind="stable")
    bounds = np.searchsorted(inv[order], np.arange(len(uniq) + 1))
    out = np.empty(n)
    for b in range(n):
        pick = rng.integers(0, len(uniq), len(uniq))
        idx = np.concatenate([order[bounds[k] : bounds[k + 1]] for k in pick])
        out[b] = _delta(y[idx], f[idx], c[idx])
    return out


def _null_pct(y: np.ndarray, f: np.ndarray, c: np.ndarray, n: int) -> float:
    """Percentile of the flagged mean among random flags matched on count within each cell."""
    rng = np.random.default_rng(SEED)
    groups = [np.flatnonzero(c == u) for u in np.unique(c)]
    counts = [int(f[g].sum()) for g in groups]
    obs = y[f].mean()
    draws = np.empty(n)
    for b in range(n):
        idx = np.concatenate([rng.choice(g, k, replace=False) for g, k in zip(groups, counts) if k])
        draws[b] = y[idx].mean()
    return float(100.0 * (draws < obs).mean())


def score(
    d: pd.DataFrame,
    flag: np.ndarray | pd.Series,
    defined: np.ndarray | pd.Series | None,
    *,
    trial_id: int | None,
    name: str,
    mechanism: str,
    sign: int,
    rnd: int,
    block: str = "discovery",
    n_boot: int = N_BOOT,
    log: bool = True,
) -> dict:
    """Score one rule on one block and append it to trials.csv."""
    flag = np.asarray(flag, dtype=bool)
    ok = np.ones(len(d), bool) if defined is None else np.asarray(defined, dtype=bool)
    ok = ok & (d["im_bin"].to_numpy() >= 0) & np.isfinite(d[Y].to_numpy(float))
    s = d[ok]
    f = flag[ok]
    y = s[Y].to_numpy(float)
    c = s["cell"].to_numpy(float)
    res: dict = {
        "trial_id": trial_id, "round": rnd, "hypothesis": name, "mechanism": mechanism,
        "predicted_sign": sign, "block": block, "n_scored": int(len(s)), "n_flagged": int(f.sum()),
    }  # fmt: skip
    if f.sum() < 30 or (~f).sum() < 30:
        res["verdict"] = "not scorable (fewer than 30 flagged or unflagged)"
        print(f"[{trial_id}] {name}: scored {len(s)}, flagged {int(f.sum())}: too few")
    else:
        dl = _delta(y, f, c)
        bt = _boot(y, f, c, s["announce_date"].to_numpy(), n_boot)
        bt = bt[np.isfinite(bt)]
        lo, hi = np.quantile(bt, [0.025, 0.975])
        t = dl / bt.std(ddof=1)
        npct = _null_pct(y, f, c, n_boot)
        subs = {}
        for k, (a, b) in SUBPERIODS.items():
            m = s["year"].between(a, b).to_numpy()
            subs[k] = _delta(y[m], f[m], c[m]) if m.sum() else float("nan")
        loser = y <= np.quantile(y, 0.05)
        signed_null = npct if sign > 0 else 100.0 - npct
        if block == "discovery":
            same = all(np.isfinite(v) and np.sign(v) == sign for v in subs.values())
            passed = (np.sign(dl) == sign) and (lo > 0 or hi < 0) and signed_null >= 95 and same
            verdict = "pass discovery" if passed else "fail discovery"
        else:
            passed = (np.sign(dl) == sign) and abs(t) >= 3 and signed_null >= 95
            verdict = "confirmed" if passed else "not confirmed"
        res.update(
            delta_prem=dl, ci_low=lo, ci_high=hi, t=t, null_pct=npct,
            delta_margin=_delta(s["pnl_margin"].to_numpy(float), f, c),
            delta_2013_17=subs.get("2013-17"), delta_2018_21=subs.get("2018-21"),
            losers_flagged=int((loser & f).sum()), losers_total=int(loser.sum()),
            ordinary_flagged=int((~loser & f).sum()),
            ratio_flagged=float(s["ratio"].to_numpy()[f].mean()),
            ratio_unflagged=float(s["ratio"].to_numpy()[~f].mean()),
            im_flagged=float(s["implied_move"].to_numpy()[f].mean()),
            im_unflagged=float(s["implied_move"].to_numpy()[~f].mean()),
            verdict=verdict,
        )  # fmt: skip
        print(
            f"[{trial_id}] {name} ({block}): scored {len(s)}, flagged {int(f.sum())}, "
            f"Delta {dl:+.4f} [{lo:+.4f}, {hi:+.4f}] t {t:+.2f} null {npct:.1f} "
            f"margin {res['delta_margin']:+.4f} sub {subs.get('2013-17', float('nan')):+.3f}/"
            f"{subs.get('2018-21', float('nan')):+.3f} losers {res['losers_flagged']}/"
            f"{res['losers_total']} ordinary {res['ordinary_flagged']} "
            f"ratio {res['ratio_flagged']:.2f}/{res['ratio_unflagged']:.2f} -> {verdict}"
        )
    if log and trial_id is not None:
        new = not TRIALS.exists()
        with TRIALS.open("a", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=TRIAL_FIELDS)
            if new:
                w.writeheader()
            w.writerow({k: res.get(k, "") for k in TRIAL_FIELDS})
    return res


def causal_pct(values: pd.Series, dates: pd.Series, min_prior: int = 200) -> np.ndarray:
    """Percentile of each value among values of strictly earlier announcement dates."""
    v = values.to_numpy(float)
    dt = pd.to_datetime(dates).to_numpy()
    order = np.argsort(dt, kind="stable")
    out = np.full(len(v), np.nan)
    seen: list[float] = []
    i = 0
    while i < len(order):
        j = i
        while j < len(order) and dt[order[j]] == dt[order[i]]:
            j += 1
        idx = order[i:j]
        if len(seen) >= min_prior:
            arr = np.sort(np.asarray(seen))
            for k in idx:
                if np.isfinite(v[k]):
                    out[k] = np.searchsorted(arr, v[k], side="right") / len(arr)
        seen.extend(float(x) for x in v[idx] if np.isfinite(x))
        i = j
    return out
