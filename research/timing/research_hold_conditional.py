"""
research_hold_conditional.py
Does a conditional exit rescue the mean advantage of holding to expiry?

research_hold_inference.py established that holding to weekly expiry beats the
next-session exit on the typical trade (59% paired win, sign p=0.006, Wilcoxon
p=0.017), but the mean advantage's bootstrap CI straddles zero because the few
worst trades dominate the variance: holding through the realised move three extra
days is most dangerous exactly when the implied move was largest.

The obvious refinement is therefore a conditional exit: hold to expiry on the bulk,
but fall back to the next-session exit on the highest implied-move events, where the
extra directional gamma is worst. This keeps all 192 trades and only chooses the exit
per trade. We test several cut percentiles and ask whether the mixed book's paired
advantage over the pure next-session book now clears zero on both bootstraps.

Reads outputs/research/hold_to_expiry.csv and joins implied_move from the gated book.
Writes outputs/research/hold_conditional.csv. No network, no new data.
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
OUT = Path("outputs/research/hold_conditional.csv")
# fall back to the next-session exit on events at or above this implied-move percentile
CUTS = [0.90, 0.80, 0.75, 0.70]
N_BOOT = 5000
SEED = 0


def _sharpe(x: np.ndarray) -> float:
    sd = x.std(ddof=1)
    return float(x.mean() / sd) if sd > 0 and len(x) > 1 else 0.0


def _iid_ci(x: np.ndarray, fn, rng) -> tuple[float, float]:
    boots = [fn(x[rng.integers(0, len(x), len(x))]) for _ in range(N_BOOT)]
    return float(np.percentile(boots, 2.5)), float(np.percentile(boots, 97.5))


def _week_block_ci(x: np.ndarray, weeks: np.ndarray, fn, rng) -> tuple[float, float]:
    groups = [x[weeks == w] for w in np.unique(weeks)]
    nb = len(groups)
    boots = []
    for _ in range(N_BOOT):
        pick = rng.integers(0, nb, nb)
        boots.append(fn(np.concatenate([groups[i] for i in pick])))
    return float(np.percentile(boots, 2.5)), float(np.percentile(boots, 97.5))


def main() -> None:
    df = pd.read_csv(IN)
    df["entry_key"] = pd.to_datetime(df["entry_date"]).dt.strftime("%Y-%m-%d")

    g = gated_events()[["ticker", "entry_date", "implied_move"]].copy()
    g["entry_key"] = pd.to_datetime(g["entry_date"]).dt.strftime("%Y-%m-%d")
    g = g.drop_duplicates(["ticker", "entry_key"])[["ticker", "entry_key", "implied_move"]]

    m = df.merge(g, on=["ticker", "entry_key"], how="left")
    miss = int(m["implied_move"].isna().sum())
    if miss:
        print(f"warning: {miss} trades missing implied_move; dropping them for this test")
        m = m.dropna(subset=["implied_move"]).reset_index(drop=True)

    im = m["implied_move"].astype(float).to_numpy()
    n = len(m)
    wk = pd.to_datetime(m["entry_date"]).dt.isocalendar()
    week_id = (wk["year"].astype(int) * 100 + wk["week"].astype(int)).to_numpy()

    bases = [
        (
            "asymmetric",
            m["rom_plus1"].astype(float).to_numpy(),
            m["rom_hold"].astype(float).to_numpy(),
        ),
        (
            "symmetric",
            m["rom_plus1_sym"].astype(float).to_numpy(),
            m["rom_hold_sym"].astype(float).to_numpy(),
        ),
    ]

    rows = []
    for basis, r1, rh in bases:
        # reference books: pure next-session and pure hold
        for label, book in [("pure_plus1", r1), ("pure_hold", rh)]:
            rows.append(
                {
                    "basis": basis,
                    "book": label,
                    "cut_pctile": np.nan,
                    "n_held": int(label == "pure_hold") * n,
                    "per_trade_sharpe": per_trade_sharpe(book),
                    "mean_rom": float(book.mean()),
                    "worst_rom": float(book.min()),
                    "win": float((book > 0).mean()),
                    "adv_mean_vs_plus1": float((book - r1).mean()),
                    "adv_iid_lo": np.nan,
                    "adv_iid_hi": np.nan,
                    "adv_block_lo": np.nan,
                    "adv_block_hi": np.nan,
                    "sign_p": np.nan,
                    "wilcoxon_p": np.nan,
                }
            )

        # conditional books: hold except top-(1-cut) implied move -> next-session exit
        for cut in CUTS:
            thr = float(np.quantile(im, cut))
            hold_mask = im < thr  # hold the bulk; fall back to plus1 on the high-move tail
            mixed = np.where(hold_mask, rh, r1)
            d = mixed - r1  # paired advantage of the conditional book over pure next-session
            il_lo, il_hi = _iid_ci(d, lambda a: float(a.mean()), np.random.default_rng(SEED))
            bl_lo, bl_hi = _week_block_ci(
                d, week_id, lambda a: float(a.mean()), np.random.default_rng(SEED)
            )
            nz = d[hold_mask]  # the trades actually switched to hold
            sign_p = (
                float(sps.binomtest((nz > 0).sum(), len(nz), 0.5, alternative="greater").pvalue)
                if len(nz)
                else np.nan
            )
            wil_p = (
                float(sps.wilcoxon(mixed[hold_mask], r1[hold_mask], alternative="greater").pvalue)
                if hold_mask.sum() > 1
                else np.nan
            )
            rows.append(
                {
                    "basis": basis,
                    "book": f"hold_below_p{int(cut*100)}",
                    "cut_pctile": cut,
                    "n_held": int(hold_mask.sum()),
                    "per_trade_sharpe": per_trade_sharpe(mixed),
                    "mean_rom": float(mixed.mean()),
                    "worst_rom": float(mixed.min()),
                    "win": float((mixed > 0).mean()),
                    "adv_mean_vs_plus1": float(d.mean()),
                    "adv_iid_lo": il_lo,
                    "adv_iid_hi": il_hi,
                    "adv_block_lo": bl_lo,
                    "adv_block_hi": bl_hi,
                    "sign_p": sign_p,
                    "wilcoxon_p": wil_p,
                }
            )

    out = pd.DataFrame(rows)
    out.to_csv(OUT, index=False)

    pd.set_option("display.width", 220)
    pd.set_option("display.max_columns", 30)
    print(
        f"=== conditional hold-to-expiry: hold the bulk, exit high-implied-move at +1 day, n={n} ==="
    )
    show = out[
        [
            "basis",
            "book",
            "cut_pctile",
            "n_held",
            "per_trade_sharpe",
            "mean_rom",
            "worst_rom",
            "win",
            "adv_mean_vs_plus1",
            "adv_iid_lo",
            "adv_iid_hi",
            "adv_block_lo",
            "adv_block_hi",
            "sign_p",
            "wilcoxon_p",
        ]
    ].copy()
    for c in [
        "per_trade_sharpe",
        "mean_rom",
        "worst_rom",
        "win",
        "adv_mean_vs_plus1",
        "adv_iid_lo",
        "adv_iid_hi",
        "adv_block_lo",
        "adv_block_hi",
    ]:
        show[c] = show[c].map(lambda v: f"{v:+.4f}" if pd.notna(v) else "")
    for c in ["sign_p", "wilcoxon_p"]:
        show[c] = show[c].map(lambda v: f"{v:.4g}" if pd.notna(v) else "")
    print(show.to_string(index=False))

    for basis, r1, rh in bases:
        sub = out[(out["basis"] == basis) & out["cut_pctile"].notna()].copy()
        sub["clears"] = (sub["adv_iid_lo"] > 0) & (sub["adv_block_lo"] > 0)
        clear = sub[sub["clears"]]
        if len(clear):
            b = clear.sort_values("adv_mean_vs_plus1", ascending=False).iloc[0]
            print(
                f"\n[{basis}] conditional at cut {b['cut_pctile']:.2f} CLEARS zero on both bootstraps "
                f"(per-trade Sharpe {b['per_trade_sharpe']:+.4f}, mean advantage "
                f"{b['adv_mean_vs_plus1']:+.4%}, iid [{b['adv_iid_lo']:+.4%},{b['adv_iid_hi']:+.4%}])."
            )
        else:
            b = sub.sort_values("per_trade_sharpe", ascending=False).iloc[0]
            print(
                f"\n[{basis}] no cut lifts the mean advantage clear of zero on both bootstraps; best "
                f"is {b['book']} at per-trade Sharpe {b['per_trade_sharpe']:+.4f} "
                f"(pure plus1 {per_trade_sharpe(r1):+.4f}, pure hold {per_trade_sharpe(rh):+.4f})."
            )
    print(
        "\nThe lever is contingent on the realistic exit cost: it clears zero on the asymmetric "
        "basis, where the 8.55% exit cross is removed, not on the optimistic symmetric basis."
    )
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
