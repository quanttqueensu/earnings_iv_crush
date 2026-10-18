"""
research_hold_inference.py
Is the hold-to-expiry advantage over the next-session exit real, or noise?

research_hold_to_expiry.py showed hold-to-expiry lifts the realistic-cost per-trade
Sharpe from +0.014 to +0.097. Because both exits are measured on the SAME 192 trades,
the comparison is paired, which is far more powerful than either absolute Sharpe: the
common earnings-move risk differences out, leaving the exit-cost saving. This script
bootstraps the paired advantage and reports whether it clears zero.

Reads outputs/research/hold_to_expiry.csv. Writes outputs/research/hold_inference.csv.
No network, no new data.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from scipy import stats as sps  # noqa: E402

IN = Path("outputs/research/hold_to_expiry.csv")
OUT = Path("outputs/research/hold_inference.csv")
N_BOOT = 5000
SEED = 0


def _sharpe(x: np.ndarray) -> float:
    sd = x.std(ddof=1)
    return float(x.mean() / sd) if sd > 0 and len(x) > 1 else 0.0


def _iid_ci(x: np.ndarray, fn, rng) -> tuple[float, float]:
    boots = [fn(x[rng.integers(0, len(x), len(x))]) for _ in range(N_BOOT)]
    return tuple(np.percentile(boots, [2.5, 97.5]))


def _week_block_ci(x: np.ndarray, weeks: np.ndarray, fn, rng) -> tuple[float, float]:
    groups = [x[weeks == w] for w in np.unique(weeks)]
    nb = len(groups)
    boots = []
    for _ in range(N_BOOT):
        pick = rng.integers(0, nb, nb)
        boots.append(fn(np.concatenate([groups[i] for i in pick])))
    return tuple(np.percentile(boots, [2.5, 97.5]))


def main() -> None:
    df = pd.read_csv(IN)
    r1 = df["rom_plus1"].astype(float).to_numpy()
    rh = df["rom_hold"].astype(float).to_numpy()
    d = rh - r1  # paired per-trade advantage of holding to expiry
    n = len(d)

    wk = pd.to_datetime(df["entry_date"]).dt.isocalendar()
    week_id = (wk["year"].astype(int) * 100 + wk["week"].astype(int)).to_numpy()

    # paired mean advantage (return on margin units)
    mean_d = float(d.mean())
    md_lo, md_hi = _iid_ci(d, lambda a: float(a.mean()), np.random.default_rng(SEED))
    mdw_lo, mdw_hi = _week_block_ci(
        d, week_id, lambda a: float(a.mean()), np.random.default_rng(SEED)
    )

    # per-trade Sharpe of each book and of the paired difference series
    sh1, shh, shd = _sharpe(r1), _sharpe(rh), _sharpe(d)
    shd_lo, shd_hi = _iid_ci(d, _sharpe, np.random.default_rng(SEED + 1))

    # paired win rate and sign test
    paired_win = float((d > 0).mean())
    sign_p = float(sps.binomtest((d > 0).sum(), n, 0.5, alternative="greater").pvalue)
    # Wilcoxon signed-rank (non-parametric paired test, robust to the fat tail)
    wilcox_p = float(sps.wilcoxon(rh, r1, alternative="greater").pvalue)

    # probabilistic-Sharpe-style: P(true paired Sharpe > 0) under a normal approx with
    # skew/kurtosis deflation on the difference series
    g1 = float(sps.skew(d, bias=False))
    g2 = float(sps.kurtosis(d, fisher=False, bias=False))  # non-excess
    denom = np.sqrt(max(1e-9, 1 - g1 * shd + (g2 - 1) / 4 * shd**2))
    psr = float(sps.norm.cdf(shd * np.sqrt(n - 1) / denom))

    rows = [
        {
            "metric": "mean_advantage_rom",
            "value": mean_d,
            "ci_lo": md_lo,
            "ci_hi": md_hi,
            "method": "iid",
        },
        {
            "metric": "mean_advantage_rom",
            "value": mean_d,
            "ci_lo": mdw_lo,
            "ci_hi": mdw_hi,
            "method": "week_block",
        },
        {
            "metric": "sharpe_plus1",
            "value": sh1,
            "ci_lo": np.nan,
            "ci_hi": np.nan,
            "method": "point",
        },
        {
            "metric": "sharpe_hold",
            "value": shh,
            "ci_lo": np.nan,
            "ci_hi": np.nan,
            "method": "point",
        },
        {
            "metric": "sharpe_paired_diff",
            "value": shd,
            "ci_lo": shd_lo,
            "ci_hi": shd_hi,
            "method": "iid",
        },
        {
            "metric": "paired_win_rate",
            "value": paired_win,
            "ci_lo": np.nan,
            "ci_hi": np.nan,
            "method": "point",
        },
        {
            "metric": "sign_test_p_greater",
            "value": sign_p,
            "ci_lo": np.nan,
            "ci_hi": np.nan,
            "method": "binom",
        },
        {
            "metric": "wilcoxon_p_greater",
            "value": wilcox_p,
            "ci_lo": np.nan,
            "ci_hi": np.nan,
            "method": "wilcoxon",
        },
        {
            "metric": "psr_paired_diff_gt0",
            "value": psr,
            "ci_lo": np.nan,
            "ci_hi": np.nan,
            "method": "deflated_normal",
        },
    ]
    pd.DataFrame(rows).to_csv(OUT, index=False)

    print(f"=== hold-to-expiry vs next-session exit: paired inference, n={n} ===")
    print(f"per-trade Sharpe   plus1 {sh1:+.4f}   hold {shh:+.4f}")
    print(f"mean paired advantage (ROM)  {mean_d:+.4%}")
    print(f"  iid 95% CI         [{md_lo:+.4%}, {md_hi:+.4%}]")
    print(f"  week-block 95% CI  [{mdw_lo:+.4%}, {mdw_hi:+.4%}]")
    print(
        f"Sharpe of the paired difference series  {shd:+.3f}   iid 95% CI [{shd_lo:+.3f}, {shd_hi:+.3f}]"
    )
    print(f"paired win rate (hold beats plus1)  {paired_win:.1%}")
    print(f"sign test p (hold>plus1)            {sign_p:.4g}")
    print(f"Wilcoxon signed-rank p              {wilcox_p:.4g}")
    print(f"PSR that paired advantage > 0       {psr:.3f}")
    clears = md_lo > 0 and mdw_lo > 0
    print(
        f"\nVerdict: the paired advantage {'CLEARS' if clears else 'does NOT clear'} zero on both "
        f"bootstraps; sign/Wilcoxon {'agree' if max(sign_p, wilcox_p) < 0.05 else 'mixed'}."
    )
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
