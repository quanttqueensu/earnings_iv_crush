"""
reverse_alpha_p1.py
Phase 1: map the whole profitable region, not just the cell that was chosen.

The frozen specification keeps events whose ``iv_term_spread`` sits at or above the 80th
percentile of strictly earlier events. That single number is the output of a search over
roughly 1,476 configurations, so the first honest question is not whether q=0.80 works but
what the surface around it looks like. A broad plateau, a smooth gradient and an isolated
spike are three different findings, and only the third is straightforwardly overfitting.

Because the gate is exactly a threshold on the stored ``term_rank`` column, the percentile
axis is a sweep rather than a re-mark, and neighbouring cells are nested by construction:
the q=0.75 selection strictly contains the q=0.80 selection. Nested cells cannot be
independent evidence, so the overlap column is reported to keep that visible rather than
letting adjacent-cell agreement look like corroboration.

The second axis is the move gate, ``implied_move >= ratio * fair_move``, which was the
other live parameter in the recorded trials and was dropped from the frozen spec for
failing out of sample.

Everything here runs on the discovery block only. The 2013-2018 block is not touched by any
phase before the frozen validation.

Usage:
    python research/selection/reverse_alpha_p1.py
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

TERM_GRID = np.round(np.arange(0.00, 0.96, 0.05), 2)
MOVE_GRID = [0.0, 0.9, 1.0, 1.1, 1.2, 1.3]


def move_mask(df: pd.DataFrame, ratio: float) -> np.ndarray:
    """The move gate: is the straddle priced above ``ratio`` times the fair move?"""
    im = pd.to_numeric(df["implied_move"], errors="coerce").to_numpy(dtype=float)
    fm = pd.to_numeric(df["fair_move"], errors="coerce").to_numpy(dtype=float)
    if ratio <= 0:
        return np.ones(len(df), dtype=bool)
    with np.errstate(invalid="ignore"):
        return np.nan_to_num(im >= ratio * fm, nan=False)


def surface(panel: pd.DataFrame) -> pd.DataFrame:
    """Score every cell of the term x move grid, with concentration and cost sensitivity."""
    rows: list[dict] = []
    prev: pd.DataFrame | None = None
    for mr in MOVE_GRID:
        mm = move_mask(panel, mr)
        prev = None
        for tp in TERM_GRID:
            sel = ra.gate(panel[mm], float(tp))
            if len(sel) < 10:
                continue
            row = ra.score_row(
                sel, f"term{tp:.2f}_move{mr:.1f}", term_pctl=float(tp), move_ratio=mr
            )
            # Same selection, measured execution rather than the frozen cost stack.
            meas = sel.assign(**{ra.RET: ra.rescore_measured(sel)})
            row["mean_measured"] = float(pd.to_numeric(meas[ra.RET], errors="coerce").mean())
            row["sharpe_measured"] = float(ra.score(meas, "m").sharpe if len(meas) >= 3 else np.nan)
            # Gross of all costs, to separate a pricing edge from a cost artefact.
            gr = sel.assign(**{ra.RET: pd.to_numeric(sel["rom_gross"], errors="coerce")})
            row["mean_gross"] = float(pd.to_numeric(gr[ra.RET], errors="coerce").mean())
            row["sharpe_gross"] = float(ra.score(gr, "g").sharpe)

            yr = ra.yearly(sel)
            row["years"] = len(yr)
            row["years_positive"] = int((yr["mean"] > 0).sum())
            row["worst_year"] = float(yr["mean"].min())
            row["overlap_prev_cell"] = ra.jaccard(prev, sel) if prev is not None else np.nan
            rows.append(row)
            prev = sel
    return pd.DataFrame(rows)


def classify(surf: pd.DataFrame, disjoint: pd.DataFrame) -> str:
    """Plateau, gradient or spike, decided on the term axis at the frozen move setting.

    The nested sweep is checked first but cannot settle the question on its own. A
    threshold sweep computes cumulative means of the tail above each cut, so it comes out
    monotone whenever the underlying continuous relationship is monotone, and also when a
    single extreme decile carries everything and the rest is flat. The disjoint decile sort
    separates those two, so it is what decides between a gradient and a spike.
    """
    line = surf[surf["move_ratio"] == 0.0].sort_values("term_pctl")
    if line.empty or disjoint.empty:
        return "unclassifiable"
    rho_sweep = float(line["term_pctl"].corr(line["sharpe"], method="spearman"))
    rho_bins = float(
        disjoint["bin"].corr(disjoint["mean"], method="spearman") if len(disjoint) > 2 else np.nan
    )
    top = disjoint.sort_values("bin").iloc[-1]
    rest = disjoint.sort_values("bin").iloc[:-1]

    if rho_sweep > 0.8 and np.isfinite(rho_bins) and rho_bins > 0.6:
        return "smooth gradient: monotone in the parameter AND across disjoint bins"
    if top["mean"] > 2.0 * float(rest["mean"].max()):
        return (
            "tail effect: the extreme bin carries the book and the remaining bins are "
            "flat, so the monotone sweep is cumulative-mean arithmetic, not a gradient"
        )
    if rho_sweep > 0.8:
        return "gradient in the nested sweep only; disjoint bins do not confirm it"
    return "broad plateau or unstructured"


def main() -> None:
    panel = load_panel()
    disc = panel[panel["block"] == DISCOVERY].reset_index(drop=True)
    print(f"discovery block: {len(disc)} priced events, {disc['ticker'].nunique()} names\n")

    print("=== PHASE 1: response surface over the term x move grid ===")
    surf = surface(disc)
    ra.write(surf, "response_surface.csv")

    line = surf[surf["move_ratio"] == 0.0].sort_values("term_pctl")
    print("\nterm axis alone (move gate off), frozen cost basis:")
    ra.show(
        line,
        [
            "term_pctl",
            "n",
            "n_dates",
            "mean",
            "sharpe",
            "hit",
            "ci_lo",
            "ci_hi",
            "sharpe_gross",
            "sharpe_measured",
            "years_positive",
            "top5_share",
            "overlap_prev_cell",
        ],
    )

    # Disjoint bins. The nested sweep above shares events between adjacent cells, so it
    # cannot tell a genuine gradient from one extreme decile carrying the whole book.
    # Binned globally, not within quarter. ``term_rank`` is already an expanding percentile
    # against the event's own past, so it is time-normalised by construction; imposing a
    # second within-quarter normalisation only starves the bins.
    print("\ndisjoint decile sort on term_rank (global bins; the rank is already causal):")
    dec = ra.quantile_sort(disc, "term_rank", 10, by_period=None)
    ra.show(dec, ["bin", "n", "n_dates", "mean", "sharpe", "hit", "ci_lo", "ci_hi", "signal_mean"])
    rho_bins = float(dec["bin"].corr(dec["mean"], method="spearman")) if len(dec) > 2 else np.nan
    print(f"  Spearman(decile, mean RoM) = {rho_bins:+.4f}")
    rho_cont, n_cont = ra.spearman(disc, "term_rank")
    print(f"  Spearman(term_rank, RoM) event-level = {rho_cont:+.4f} on n={n_cont}")
    ra.write(dec, "response_surface_deciles.csv")

    verdict = classify(surf, dec)
    peak = line.loc[line["sharpe"].idxmax()]
    print(
        f"\n  peak cell            : q={peak['term_pctl']:.2f}  Sharpe {peak['sharpe']:+.4f}  N={int(peak['n'])}"
    )
    frozen = line[np.isclose(line["term_pctl"], 0.80)].iloc[0]
    print(f"  frozen cell (q=0.80) : Sharpe {frozen['sharpe']:+.4f}  N={int(frozen['n'])}")
    rho = float(line["term_pctl"].corr(line["sharpe"], method="spearman"))
    print(f"  Spearman(term_pctl, Sharpe) across the axis: {rho:+.4f}")
    print(f"  SHAPE: {verdict}")

    best = surf.loc[surf["sharpe"].idxmax()]
    print(
        f"\n  best cell anywhere on the 2-D grid: term={best['term_pctl']:.2f} "
        f"move={best['move_ratio']:.1f}  Sharpe {best['sharpe']:+.4f}  N={int(best['n'])}"
    )

    ra.ledger_append(
        hypothesis_id="H01",
        hypothesis="The q=0.80 term gate sits on a broad, stable region rather than an isolated cell",
        mechanism="If the gate captures an economic state, neighbouring thresholds should "
        "capture a weakened version of it rather than collapsing",
        variables="term_rank, implied_move/fair_move",
        sample=f"{DISCOVERY}, n={len(disc)} ungated",
        parameters=f"term_pctl {TERM_GRID.min()}-{TERM_GRID.max()} step 0.05; move_ratio {MOVE_GRID}",
        conceived="before (planned as Phase 1)",
        result=f"peak Sharpe {peak['sharpe']:+.4f} at q={peak['term_pctl']:.2f}; "
        f"frozen q=0.80 {frozen['sharpe']:+.4f}; Spearman(q, Sharpe)={rho:+.4f}",
        inference=verdict,
        verdict="continue",
        reason="Shape of the surface determines whether a latent variable is worth seeking",
        next="H02: describe what separates selected from unselected events",
    )
    print(f"\n  ledger -> {ra.LEDGER}")


if __name__ == "__main__":
    main()
