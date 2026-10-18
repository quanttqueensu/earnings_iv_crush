"""
research_hold_holdout.py
Does the conditional-exit cut survive out of sample, or is it in-sample selection?

research_hold_conditional.py chooses the implied-move cut percentile over a four-point
grid on all 192 trades, so the winning cut (hold below the 75th percentile, exit the top
quartile at the next session) carries in-sample selection. This script retires that
caveat with a clean temporal split: the cut percentile is chosen on an early in-sample
window only, frozen, then applied to a held-back later window and scored there.

The frozen rule is a percentile rule ("exit the top (1 - cut) by implied move"); on the
held-out window the threshold is the same percentile of the held-out implied-move
distribution, so the rule adapts to the later regime rather than reusing an early
absolute level. This evaluates whether the selected rule has out-of-sample value; live
causal deployment (an expanding per-trade percentile) is the forward paper test's job.

Reads outputs/research/hold_to_expiry.csv (both cost bases) and joins implied_move from
the gated book. Writes outputs/research/hold_holdout.csv. No network, no new data.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from scipy import stats as sps  # noqa: E402

from research.timing.research_lossstudy_common import gated_events, per_trade_sharpe  # noqa: E402

IN = Path("outputs/research/hold_to_expiry.csv")
OUT = Path("outputs/research/hold_holdout.csv")
SPLIT = "2023-01-01"  # trades before this date train the cut; from this date test it
CUTS = [0.90, 0.80, 0.75, 0.70]
N_BOOT = 5000
SEED = 0


def _iid_ci(x: np.ndarray, rng) -> tuple[float, float]:
    boots = [float(x[rng.integers(0, len(x), len(x))].mean()) for _ in range(N_BOOT)]
    return float(np.percentile(boots, 2.5)), float(np.percentile(boots, 97.5))


def _week_block_ci(x: np.ndarray, weeks: np.ndarray, rng) -> tuple[float, float]:
    groups = [x[weeks == w] for w in np.unique(weeks)]
    nb = len(groups)
    boots = []
    for _ in range(N_BOOT):
        pick = rng.integers(0, nb, nb)
        boots.append(float(np.concatenate([groups[i] for i in pick]).mean()))
    return float(np.percentile(boots, 2.5)), float(np.percentile(boots, 97.5))


def _conditional(r1: np.ndarray, rh: np.ndarray, im: np.ndarray, cut: float) -> np.ndarray:
    """Mixed book: hold to expiry below the cut percentile of implied move, else +1-day."""
    thr = float(np.quantile(im, cut))
    return np.where(im < thr, rh, r1)


def main() -> None:
    df = pd.read_csv(IN)
    df["entry_key"] = pd.to_datetime(df["entry_date"]).dt.strftime("%Y-%m-%d")

    g = gated_events()[["ticker", "entry_date", "implied_move"]].copy()
    g["entry_key"] = pd.to_datetime(g["entry_date"]).dt.strftime("%Y-%m-%d")
    g = g.drop_duplicates(["ticker", "entry_key"])[["ticker", "entry_key", "implied_move"]]

    m = df.merge(g, on=["ticker", "entry_key"], how="left").dropna(subset=["implied_move"])
    m = m.sort_values("entry_date").reset_index(drop=True)

    edate = pd.to_datetime(m["entry_date"])
    is_in = (edate < SPLIT).to_numpy()
    is_out = ~is_in
    n_in, n_out = int(is_in.sum()), int(is_out.sum())

    wk = edate.dt.isocalendar()
    week_id = (wk["year"].astype(int) * 100 + wk["week"].astype(int)).to_numpy()

    rows = []
    for basis in ["asymmetric", "symmetric"]:
        suf = "" if basis == "asymmetric" else "_sym"
        r1 = m[f"rom_plus1{suf}"].astype(float).to_numpy()
        rh = m[f"rom_hold{suf}"].astype(float).to_numpy()
        im = m["implied_move"].astype(float).to_numpy()

        # choose the cut on the in-sample window only, by conditional per-trade Sharpe
        in_scores = {
            cut: per_trade_sharpe(_conditional(r1[is_in], rh[is_in], im[is_in], cut))
            for cut in CUTS
        }
        best_cut = max(in_scores, key=in_scores.get)

        # freeze it and score the held-out window
        mixed_out = _conditional(r1[is_out], rh[is_out], im[is_out], best_cut)
        plus1_out = r1[is_out]
        d_out = mixed_out - plus1_out
        rng = np.random.default_rng(SEED)
        il_lo, il_hi = _iid_ci(d_out, rng)
        bl_lo, bl_hi = _week_block_ci(d_out, week_id[is_out], np.random.default_rng(SEED))
        held = im[is_out] < float(np.quantile(im[is_out], best_cut))
        sign_p = (
            float(
                sps.binomtest(
                    int((d_out[held] > 0).sum()), int(held.sum()), 0.5, alternative="greater"
                ).pvalue
            )
            if held.sum()
            else np.nan
        )
        wil_p = (
            float(sps.wilcoxon(mixed_out[held], plus1_out[held], alternative="greater").pvalue)
            if held.sum() > 1
            else np.nan
        )
        rows.append(
            {
                "basis": basis,
                "chosen_cut_in_sample": best_cut,
                "in_sample_best_sharpe": in_scores[best_cut],
                "n_in": n_in,
                "n_out": n_out,
                "oos_plus1_sharpe": per_trade_sharpe(plus1_out),
                "oos_conditional_sharpe": per_trade_sharpe(mixed_out),
                "oos_mean_adv": float(d_out.mean()),
                "oos_adv_iid_lo": il_lo,
                "oos_adv_iid_hi": il_hi,
                "oos_adv_block_lo": bl_lo,
                "oos_adv_block_hi": bl_hi,
                "oos_sign_p": sign_p,
                "oos_wilcoxon_p": wil_p,
            }
        )

    out = pd.DataFrame(rows)
    out.to_csv(OUT, index=False)

    print(
        f"=== held-out confirmation of the conditional cut (split {SPLIT}, n_in={n_in}, n_out={n_out}) ==="
    )
    for _, r in out.iterrows():
        better = r["oos_conditional_sharpe"] > r["oos_plus1_sharpe"]
        clears = r["oos_adv_iid_lo"] > 0 and r["oos_adv_block_lo"] > 0
        print(
            f"\n[{r['basis']}] cut chosen in-sample: p{int(r['chosen_cut_in_sample']*100)} "
            f"(in-sample conditional Sharpe {r['in_sample_best_sharpe']:+.3f})"
        )
        print(
            f"  out-of-sample: plus1 {r['oos_plus1_sharpe']:+.3f} -> conditional "
            f"{r['oos_conditional_sharpe']:+.3f}  ({'beats' if better else 'does not beat'} the next-session book)"
        )
        print(
            f"  OOS mean advantage {r['oos_mean_adv']:+.4%}  iid [{r['oos_adv_iid_lo']:+.4%},"
            f"{r['oos_adv_iid_hi']:+.4%}]  block [{r['oos_adv_block_lo']:+.4%},{r['oos_adv_block_hi']:+.4%}]"
            f"  {'CLEARS zero' if clears else 'straddles zero'}"
        )
        print(f"  OOS sign p {r['oos_sign_p']:.4g}   Wilcoxon p {r['oos_wilcoxon_p']:.4g}")
    print(f"\nwrote {OUT}")


if __name__ == "__main__":
    main()
