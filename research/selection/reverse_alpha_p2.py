"""
reverse_alpha_p2.py
Phases 2 and 3: what the gate selects, and whether one economic variable replaces it.

Phase 1 established that the profitable region is the top decile of ``term_rank`` and that
the nine deciles below it are flat. So the question is not "what does a high term spread
predict" but "what is different about the events in that tail, and is the tail a proxy for
something with a cleaner economic reading".

Phase 2 is deliberately descriptive. Fitting another model to the selection would answer a
different question: not what the gate picks, but what a second model can be trained to
mimic. Standardised mean differences and rank correlations are enough to see which
observables move as one walks up the response surface.

Phase 3 then tests candidate latent variables. Each has to be stated as economics before
it is scored, and each is scored the same way as the gate itself, so a "better" variable
means better on the same yardstick rather than better on a yardstick chosen to suit it.

The candidates, and why each is on the list:

``implied_jump``   the event move the term structure prices, in fraction-of-spot units.
                   The term spread's economic content once the tenor is divided out. If
                   the gate works because it finds big priced events, this is the variable.
``event_share``    the share of front-month variance attributable to the event. Scale-free
                   in a different way: it asks how *concentrated* the front month is on the
                   announcement, not how large the announcement is.
``jump_richness``  the priced event jump over the name's own trailing realised event move.
                   If the gate works because it finds events priced richly against what the
                   name actually does, this is the variable, and it is the one with a
                   textbook overpricing interpretation.
``move_richness``  the same ratio built on the whole straddle rather than the event
                   component, carried so the two are told apart rather than assumed equal.
``vol_premium``    front ATM IV less trailing realised vol (Goyal and Saretto 2009).
``variance_risk_premium``  the same in variance units (Bollerslev, Tauchen and Zhou 2009).

Usage:
    python research/selection/reverse_alpha_p2.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import research.selection.reverse_alpha_lib as ra  # noqa: E402
from research.selection.reverse_alpha_panel import load_panel  # noqa: E402

DISCOVERY = "discovery_2019_2024"

#: Every observable available at entry, plus outcome variables kept separate and clearly
#: labelled so a post-event quantity can never be mistaken for a signal.
AT_ENTRY = [
    "iv_term_spread",
    "front_atm_iv",
    "back_atm_iv",
    "implied_move",
    "trailing_rv",
    "skew_25d",
    "vol_premium",
    "variance_risk_premium",
    "bkm_skew",
    "bkm_kurt",
    "t_entry",
    "spot_entry",
    "credit_mkt",
    "contracts",
    "margin",
    "fair_move",
    "event_var",
    "implied_jump",
    "event_share",
    "front_var",
    "name_move_hist",
    "jump_richness",
    "move_richness",
]
POST_EVENT = ["realised_move", "crush", "exit_mkt"]

CANDIDATES = [
    "term_rank",
    "iv_term_spread",
    "implied_jump",
    "event_share",
    "jump_richness",
    "move_richness",
    "vol_premium",
    "variance_risk_premium",
    "implied_move",
]


def smd(sel: pd.Series, rest: pd.Series) -> float:
    """Standardised mean difference, pooled standard deviation."""
    a, b = sel.dropna(), rest.dropna()
    if len(a) < 3 or len(b) < 3:
        return float("nan")
    sd = np.sqrt((a.var(ddof=1) + b.var(ddof=1)) / 2)
    return float((a.mean() - b.mean()) / sd) if sd > 0 else float("nan")


def selected_vs_unselected(disc: pd.DataFrame) -> pd.DataFrame:
    """Describe the selection at the frozen cut and at the top decile it really lives in."""
    rows = []
    cuts = {"frozen_q080": 0.80, "top_decile_q090": 0.90, "top_ventile_q095": 0.95}
    for name, q in cuts.items():
        sel = disc[disc["term_rank"] >= q]
        rest = disc[disc["term_rank"] < q]
        for col in [*AT_ENTRY, *POST_EVENT]:
            if col not in disc.columns:
                continue
            a = pd.to_numeric(sel[col], errors="coerce")
            b = pd.to_numeric(rest[col], errors="coerce")
            rows.append(
                {
                    "cut": name,
                    "variable": col,
                    "kind": "post-event" if col in POST_EVENT else "at-entry",
                    "mean_selected": float(a.mean()),
                    "mean_unselected": float(b.mean()),
                    "median_selected": float(a.median()),
                    "median_unselected": float(b.median()),
                    "smd": smd(a, b),
                    "n_selected": int(a.notna().sum()),
                }
            )
    return pd.DataFrame(rows)


def gradient_along_surface(disc: pd.DataFrame) -> pd.DataFrame:
    """How each observable moves as the threshold walks up the response surface.

    This is the Phase 2 question stated precisely: which characteristics change
    monotonically from losing cells to profitable ones. A variable that barely moves is not
    what the gate is selecting on, whatever its economic appeal.
    """
    grid = np.round(np.arange(0.0, 0.96, 0.05), 2)
    rows = []
    for col in AT_ENTRY:
        if col not in disc.columns:
            continue
        means = []
        for q in grid:
            sel = disc[disc["term_rank"] >= q]
            means.append(float(pd.to_numeric(sel[col], errors="coerce").mean()))
        means_arr = np.array(means, dtype=float)
        ok = np.isfinite(means_arr)
        rho = (
            float(pd.Series(grid[ok]).corr(pd.Series(means_arr[ok]), method="spearman"))
            if ok.sum() > 3
            else np.nan
        )
        base, top = means_arr[0], means_arr[-1]
        rows.append(
            {
                "variable": col,
                "mean_at_q000": base,
                "mean_at_q095": top,
                "relative_shift": float((top - base) / abs(base)) if base else np.nan,
                "spearman_with_threshold": rho,
            }
        )
    return pd.DataFrame(rows).sort_values("spearman_with_threshold", ascending=False)


def candidate_table(disc: pd.DataFrame) -> pd.DataFrame:
    """Score each candidate latent variable on the same yardstick as the gate itself."""
    rows = []
    for sig in CANDIDATES:
        if sig not in disc.columns:
            continue
        d = disc.dropna(subset=[sig])
        rho, n = ra.spearman(d, sig)
        dec = ra.quantile_sort(d, sig, 10, by_period=None)
        if dec.empty:
            continue
        top = dec.sort_values("bin").iloc[-1]
        rest = dec.sort_values("bin").iloc[:-1]
        # Score the top-20% selection on each candidate, matched in size to the frozen gate
        # so a candidate cannot look better merely by trading a smaller, more extreme book.
        thresh = pd.to_numeric(d[sig], errors="coerce").quantile(0.80)
        sel = d[pd.to_numeric(d[sig], errors="coerce") >= thresh]
        s = ra.score(sel, sig) if len(sel) >= 10 else None
        rows.append(
            {
                "signal": sig,
                "n": n,
                "spearman_ret": rho,
                "decile_spearman": float(dec["bin"].corr(dec["mean"], method="spearman")),
                "top_decile_mean": float(top["mean"]),
                "top_decile_hit": float(top["hit"]),
                "rest_mean": float(rest["mean"].mean()),
                "monotone_frac": ra.monotone_frac(dec),
                "top20_n": int(s.n) if s else 0,
                "top20_mean": float(s.mean) if s else np.nan,
                "top20_sharpe": float(s.sharpe) if s else np.nan,
                "top20_hit": float(s.hit) if s else np.nan,
                "top20_ci_lo": float(s.ci_lo) if s else np.nan,
                "top20_ci_hi": float(s.ci_hi) if s else np.nan,
            }
        )
    return pd.DataFrame(rows).sort_values("top20_sharpe", ascending=False)


def main() -> None:
    panel = load_panel()
    disc = panel[panel["block"] == DISCOVERY].reset_index(drop=True)

    print("=== PHASE 2: what does the gate actually select? ===")
    sv = selected_vs_unselected(disc)
    ra.write(sv, "selected_vs_unselected.csv")

    frozen = sv[sv["cut"] == "frozen_q080"].copy()
    frozen["abs_smd"] = frozen["smd"].abs()
    print("\nstandardised mean differences at the frozen q=0.80 cut, largest first:")
    ra.show(
        frozen.sort_values("abs_smd", ascending=False).head(14),
        ["variable", "kind", "mean_selected", "mean_unselected", "smd"],
    )

    print("\nhow each observable moves as the threshold walks up the surface:")
    grad = gradient_along_surface(disc)
    ra.write(grad, "selection_gradient.csv")
    ra.show(
        grad.head(14),
        ["variable", "mean_at_q000", "mean_at_q095", "relative_shift", "spearman_with_threshold"],
    )

    print("\n=== PHASE 3: can one economic variable replace the gate? ===")
    cand = candidate_table(disc)
    ra.write(cand, "latent_candidates.csv")
    ra.show(
        cand,
        [
            "signal",
            "n",
            "spearman_ret",
            "decile_spearman",
            "top_decile_mean",
            "rest_mean",
            "top20_n",
            "top20_mean",
            "top20_sharpe",
            "top20_hit",
            "top20_ci_lo",
            "top20_ci_hi",
        ],
    )

    best = cand.iloc[0]
    gate_row = cand[cand["signal"] == "term_rank"].iloc[0]
    print(
        f"\n  best candidate on a size-matched top-20% book: {best['signal']} "
        f"Sharpe {best['top20_sharpe']:+.4f} (N={int(best['top20_n'])})"
    )
    print(
        f"  the gate itself                              : term_rank "
        f"Sharpe {gate_row['top20_sharpe']:+.4f} (N={int(gate_row['top20_n'])})"
    )

    ra.ledger_append(
        hypothesis_id="H02",
        hypothesis="The term gate selects a describable economic state rather than an arbitrary subset",
        mechanism="A steep front-vs-back structure prices a large announcement jump relative "
        "to the diffusive baseline",
        variables=", ".join(AT_ENTRY),
        sample=f"{DISCOVERY}, n={len(disc)}",
        parameters="cuts at q=0.80, 0.90, 0.95",
        conceived="before (planned as Phase 2)",
        result="; ".join(
            f"{r['variable']} SMD {r['smd']:+.2f}"
            for _, r in frozen.sort_values("abs_smd", ascending=False).head(5).iterrows()
        ),
        inference="the gate loads on the variables listed, in that order",
        verdict="continue",
        reason="Descriptive step; no claim tested",
        next="H03: replace the gate with a single continuous economic variable",
    )
    ra.ledger_append(
        hypothesis_id="H03",
        hypothesis="A single continuous economic variable replaces the term percentile gate",
        mechanism="If the gate proxies event-premium richness, a directly constructed "
        "richness measure should sort at least as well",
        variables=", ".join(CANDIDATES),
        sample=f"{DISCOVERY}, n={len(disc)}",
        parameters="top-20% selection on each candidate, size-matched to the frozen gate",
        conceived="before (planned as Phase 3)",
        result=f"best {best['signal']} Sharpe {best['top20_sharpe']:+.4f} N={int(best['top20_n'])}; "
        f"term_rank {gate_row['top20_sharpe']:+.4f} N={int(gate_row['top20_n'])}",
        inference="see findings",
        verdict="continue",
        reason="Candidate ranking established on the discovery block only",
        next="H04: decompose the P&L of the surviving selection",
    )


if __name__ == "__main__":
    main()
