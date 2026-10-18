"""
reverse_alpha_p4.py
Phases 4, 5, 7, 8 and 9 on the surviving candidate.

Phase 3 left one variable standing: ``jump_richness``, the event jump the term structure
prices divided by the mean absolute event move the same name has actually delivered at its
own prior announcements. This runs the rest of the adversarial programme against it, all
on the discovery block, before anything is frozen.

  4  decompose   where the P&L comes from: premium collected, the gap the realised move
                 punches through the strike, and the volatility and time value left in the
                 contract at exit. Costs are separated from all three.
  5  opposite    does the low end of the same variable behave oppositely? A monotone
                 long-short relationship is much stronger evidence than one profitable
                 tail, and a flat low end would say the tail is a curiosity.
  7  confounds   is the variable really proxying DTE, spread, premium level, price,
                 volatility level, the name, or the year? Two neutralisations are run and
                 the signal is called specification fragile if they disagree.
  8  concentrate leave-one-out over names, years and quarters, plus the contribution of the
                 largest trades. A result that needs one company is not established.
  9  execution   the real liquidity-taking round trip, selling the quoted bid and buying
                 the quoted ask on the contract actually traded, and whether the selected
                 population is more expensive than the unconditional book.

Usage:
    python research/selection/reverse_alpha_p4.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import research.selection.reverse_alpha_lib as ra  # noqa: E402
from research.selection.reverse_alpha_panel import load_panel  # noqa: E402

DISCOVERY = "discovery_2019_2024"
SIGNAL = "jump_richness"
CUT = 0.80  # top quintile, matching the frozen gate's selectivity


def selection(df: pd.DataFrame, signal: str = SIGNAL, cut: float = CUT) -> pd.DataFrame:
    """The top-``cut`` selection on a signal, over rows where the signal is defined."""
    d = df.dropna(subset=[signal])
    thresh = pd.to_numeric(d[signal], errors="coerce").quantile(cut)
    return d[pd.to_numeric(d[signal], errors="coerce") >= thresh]


# ── Phase 4 ──────────────────────────────────────────────────────────────────


def decompose(df: pd.DataFrame, label: str) -> dict:
    """Split return on margin into its mechanical components.

    Per share the short straddle earns ``credit - exit``. The exit decomposes exactly into
    the intrinsic value the realised move created and the time and volatility value still
    in the contract, so:

        pnl_per_share = credit - intrinsic_exit - residual_value_exit

    which separates the two economically distinct ways this trade loses: the underlying
    moved through the strike, or the option stayed expensive. Costs are held out of all
    three so a cost artefact cannot be read as either.
    """
    d = df.copy()
    contracts = pd.to_numeric(d["contracts"], errors="coerce")
    margin = pd.to_numeric(d["margin"], errors="coerce")
    credit = pd.to_numeric(d["credit_mkt"], errors="coerce")
    exit_ = pd.to_numeric(d["exit_mkt"], errors="coerce")
    intrinsic = pd.to_numeric(d["intr_exit"], errors="coerce")
    residual = exit_ - intrinsic

    scale = 100 * contracts / margin
    parts = {
        "premium_collected": (credit * scale).mean(),
        "gap_cost_intrinsic": (-intrinsic * scale).mean(),
        "residual_value_at_exit": (-residual * scale).mean(),
        "cost_frozen": (-pd.to_numeric(d["cost_frozen"], errors="coerce") / margin).mean(),
    }
    parts["total_check"] = sum(parts.values())
    parts["reported_mean_rom"] = pd.to_numeric(d[ra.RET], errors="coerce").mean()
    parts["label"] = label
    parts["n"] = len(d)
    return parts


def phase4(disc: pd.DataFrame) -> pd.DataFrame:
    print("\n=== PHASE 4: where does the money come from? ===")
    rows = [
        decompose(disc.dropna(subset=[SIGNAL]), "all events (signal defined)"),
        decompose(selection(disc), f"{SIGNAL} top {1 - CUT:.0%}"),
        decompose(
            disc.dropna(subset=[SIGNAL]).pipe(
                lambda d: d[
                    pd.to_numeric(d[SIGNAL], errors="coerce")
                    <= pd.to_numeric(d[SIGNAL], errors="coerce").quantile(0.20)
                ]
            ),
            f"{SIGNAL} bottom 20%",
        ),
        decompose(disc[disc["term_rank"] >= 0.80], "frozen term gate q=0.80"),
    ]
    tbl = pd.DataFrame(rows)
    cols = [
        "label",
        "n",
        "premium_collected",
        "gap_cost_intrinsic",
        "residual_value_at_exit",
        "cost_frozen",
        "total_check",
        "reported_mean_rom",
    ]
    ra.show(tbl[cols])
    ra.write(tbl[cols], "pnl_decomposition.csv")

    top = tbl[tbl["label"].str.contains("top")].iloc[0]
    bot = tbl[tbl["label"].str.contains("bottom")].iloc[0]
    print(
        f"\n  top-minus-bottom by component (return on margin):\n"
        f"    premium collected      {top['premium_collected'] - bot['premium_collected']:+.5f}\n"
        f"    gap cost (intrinsic)   {top['gap_cost_intrinsic'] - bot['gap_cost_intrinsic']:+.5f}\n"
        f"    residual value at exit {top['residual_value_at_exit'] - bot['residual_value_at_exit']:+.5f}\n"
        f"    costs                  {top['cost_frozen'] - bot['cost_frozen']:+.5f}"
    )
    return tbl


# ── Phase 5 ──────────────────────────────────────────────────────────────────


def phase5(disc: pd.DataFrame) -> pd.DataFrame:
    print("\n=== PHASE 5: does the opposite tail behave oppositely? ===")
    d = disc.dropna(subset=[SIGNAL])
    rows = []
    for k, name in ((5, "quintile"), (10, "decile")):
        tbl = ra.quantile_sort(d, SIGNAL, k, by_period=None)
        tbl["scheme"] = name
        rows.append(tbl)
        print(f"\n  {name} sort on {SIGNAL}:")
        ra.show(
            tbl, ["bin", "n", "n_dates", "mean", "sharpe", "hit", "ci_lo", "ci_hi", "signal_mean"]
        )
        rho = float(tbl["bin"].corr(tbl["mean"], method="spearman"))
        print(f"    Spearman(bin, mean) = {rho:+.4f}   upward steps = {ra.monotone_frac(tbl):.2f}")
    out = pd.concat(rows, ignore_index=True)

    q = ra.quantile_sort(d, SIGNAL, 5, by_period=None).sort_values("bin")
    lo, hi = q.iloc[0], q.iloc[-1]
    print(
        f"\n  bottom quintile mean {lo['mean']:+.5f} (Sharpe {lo['sharpe']:+.4f}, "
        f"CI [{lo['ci_lo']:+.4f},{lo['ci_hi']:+.4f}])"
    )
    print(
        f"  top quintile    mean {hi['mean']:+.5f} (Sharpe {hi['sharpe']:+.4f}, "
        f"CI [{hi['ci_lo']:+.4f},{hi['ci_hi']:+.4f}])"
    )

    # The long-short spread as an actual tradable difference, scored on paired dates so the
    # market-wide component cancels rather than being assumed away.
    thr_lo = pd.to_numeric(d[SIGNAL], errors="coerce").quantile(0.20)
    thr_hi = pd.to_numeric(d[SIGNAL], errors="coerce").quantile(0.80)
    short_leg = d[pd.to_numeric(d[SIGNAL], errors="coerce") >= thr_hi]
    long_leg = d[pd.to_numeric(d[SIGNAL], errors="coerce") <= thr_lo].copy()
    long_leg[ra.RET] = -pd.to_numeric(long_leg[ra.RET], errors="coerce")
    combined = pd.concat([short_leg, long_leg], ignore_index=True)
    s = ra.score(combined, "long-short")
    print(
        f"\n  long-short book (short the top quintile, buy the bottom): N={s.n}, "
        f"mean {s.mean:+.5f}, Sharpe {s.sharpe:+.4f}, hit {s.hit:.4f}, "
        f"CI [{s.ci_lo:+.4f}, {s.ci_hi:+.4f}]"
    )
    rho_c, n_c = ra.spearman(d, SIGNAL)
    print(f"  event-level Spearman(signal, RoM) = {rho_c:+.4f} on n={n_c}")
    ra.write(out, "monotonicity.csv")
    return out


# ── Phase 7 ──────────────────────────────────────────────────────────────────

CONTROLS = {
    "dte": ["t_entry"],
    "premium_level": ["credit_mkt"],
    "price_level": ["spot_entry"],
    "vol_level": ["front_atm_iv"],
    "trailing_vol": ["trailing_rv"],
    "name_history": ["name_move_hist"],
    "term_structure": ["iv_term_spread"],
    "everything": [
        "t_entry",
        "credit_mkt",
        "spot_entry",
        "front_atm_iv",
        "trailing_rv",
        "name_move_hist",
        "iv_term_spread",
    ],
}


def phase7(disc: pd.DataFrame) -> pd.DataFrame:
    print("\n=== PHASE 7: is it a proxy for something mechanical? ===")
    d = disc.dropna(subset=[SIGNAL]).reset_index(drop=True)
    base = ra.score(selection(d), "base")
    rows = [
        {
            "control": "none (raw signal)",
            "method": "-",
            "n": base.n,
            "mean": base.mean,
            "sharpe": base.sharpe,
            "hit": base.hit,
            "ci_lo": base.ci_lo,
            "ci_hi": base.ci_hi,
            "decile_spearman": float(
                ra.quantile_sort(d, SIGNAL, 10, by_period=None)["bin"].corr(
                    ra.quantile_sort(d, SIGNAL, 10, by_period=None)["mean"], method="spearman"
                )
            ),
        }
    ]
    for name, cols in CONTROLS.items():
        d2 = d.copy()
        d2["resid"] = ra.residualise(d2, SIGNAL, cols)
        sub = d2.dropna(subset=["resid"])
        if len(sub) < 50:
            continue
        sel = selection(sub, "resid")
        s = ra.score(sel, f"resid_{name}")
        dec = ra.quantile_sort(sub, "resid", 10, by_period=None)
        rows.append(
            {
                "control": name,
                "method": "OLS residual",
                "n": s.n,
                "mean": s.mean,
                "sharpe": s.sharpe,
                "hit": s.hit,
                "ci_lo": s.ci_lo,
                "ci_hi": s.ci_hi,
                "decile_spearman": float(dec["bin"].corr(dec["mean"], method="spearman")),
            }
        )
    # Stratified counterparts: within name and within year, which make no linearity
    # assumption about the control at all.
    for key, label in (("ticker", "within name"), ("year", "within year")):
        d2 = d.copy()
        d2["year"] = pd.to_datetime(d2[ra.DATE]).dt.year
        d2["dm"] = ra.demean_within(d2, SIGNAL, key)
        sub = d2.dropna(subset=["dm"])
        sel = selection(sub, "dm")
        s = ra.score(sel, f"within_{key}")
        dec = ra.quantile_sort(sub, "dm", 10, by_period=None)
        rows.append(
            {
                "control": label,
                "method": "group demean",
                "n": s.n,
                "mean": s.mean,
                "sharpe": s.sharpe,
                "hit": s.hit,
                "ci_lo": s.ci_lo,
                "ci_hi": s.ci_hi,
                "decile_spearman": float(dec["bin"].corr(dec["mean"], method="spearman")),
            }
        )
    tbl = pd.DataFrame(rows)
    ra.show(
        tbl,
        ["control", "method", "n", "mean", "sharpe", "hit", "ci_lo", "ci_hi", "decile_spearman"],
    )
    ra.write(tbl, "confound_tests.csv")

    survives = tbl[tbl["control"] != "none (raw signal)"]
    frac_pos = float((survives["sharpe"] > 0).mean())
    print(f"\n  neutralisations leaving a positive Sharpe: {frac_pos:.0%} of {len(survives)}")
    spread = float(survives["sharpe"].max() - survives["sharpe"].min())
    print(f"  spread of Sharpe across neutralisations: {spread:.4f}")
    if frac_pos < 1.0:
        print("  SPECIFICATION FRAGILE: at least one reasonable control flips the sign.")
    return tbl


# ── Phase 8 ──────────────────────────────────────────────────────────────────


def phase8(disc: pd.DataFrame) -> pd.DataFrame:
    print("\n=== PHASE 8: how concentrated is it? ===")
    sel = selection(disc.dropna(subset=[SIGNAL])).copy()
    sel["year"] = pd.to_datetime(sel[ra.DATE]).dt.year
    sel["quarter"] = pd.to_datetime(sel[ra.DATE]).dt.to_period("Q").astype(str)
    base = ra.score(sel, "full selection")
    rows = [
        {"drop": "nothing", "kind": "base", "n": base.n, "mean": base.mean, "sharpe": base.sharpe}
    ]

    v = pd.to_numeric(sel[ra.RET], errors="coerce")
    total = float(v.sum())
    for k in (1, 5, 10):
        rows.append(
            {
                "drop": f"top {k} trades",
                "kind": "trade",
                "n": base.n - k,
                "mean": float(v.sort_values().iloc[:-k].mean()),
                "sharpe": float(
                    v.sort_values().iloc[:-k].mean() / v.sort_values().iloc[:-k].std(ddof=1)
                ),
            }
        )
    for kind, key in (("name", "ticker"), ("year", "year"), ("quarter", "quarter")):
        for val, _ in sel.groupby(key):
            rest = sel[sel[key] != val]
            if len(rest) < 20:
                continue
            s = ra.score(rest, f"ex-{val}", n_boot=1000)
            rows.append(
                {"drop": str(val), "kind": kind, "n": s.n, "mean": s.mean, "sharpe": s.sharpe}
            )
    tbl = pd.DataFrame(rows)
    ra.write(tbl, "concentration.csv")

    by_name = sel.groupby("ticker")[ra.RET].sum().sort_values(ascending=False)
    print(
        f"\n  base: N={base.n}, Sharpe {base.sharpe:+.4f}, {base.n_names} names, {base.n_dates} dates"
    )
    print(
        f"  top 1 / 5 / 10 trades contribute {v.nlargest(1).sum()/total:.1%} / "
        f"{v.nlargest(5).sum()/total:.1%} / {v.nlargest(10).sum()/total:.1%} of total return"
    )
    print(f"  top 5 names contribute {by_name.head(5).sum()/total:.1%}")
    for kind in ("name", "year", "quarter"):
        sub = tbl[tbl["kind"] == kind]
        if sub.empty:
            continue
        worst = sub.loc[sub["sharpe"].idxmin()]
        print(
            f"  worst leave-one-{kind}-out: drop {worst['drop']} -> Sharpe {worst['sharpe']:+.4f} "
            f"(from {base.sharpe:+.4f}); {int((sub['sharpe'] > 0).sum())}/{len(sub)} stay positive"
        )
    return tbl


# ── Phase 9 ──────────────────────────────────────────────────────────────────


def phase9(disc: pd.DataFrame) -> pd.DataFrame:
    print("\n=== PHASE 9: real execution, taking liquidity on both sides ===")
    d = ra.attach_quotes(disc).dropna(subset=[SIGNAL])
    d["width_entry"] = ra.quoted_width(d, "entry")
    d["width_exit"] = ra.quoted_width(d, "exit")
    d["rom_exec"] = ra.rom_executable(d)
    d["rom_measured"] = ra.rescore_measured(d)

    rows = []
    books = {
        "all events": d,
        f"{SIGNAL} top 20%": selection(d),
        "frozen term gate q=0.80": d[d["term_rank"] >= 0.80],
    }
    for name, g in books.items():
        for basis, col in (
            ("mid, no cost", "rom_gross"),
            ("frozen model cost", ra.RET),
            ("measured fills study", "rom_measured"),
            ("quoted bid/ask taken", "rom_exec"),
        ):
            gg = g.assign(**{ra.RET: pd.to_numeric(g[col], errors="coerce")}).dropna(
                subset=[ra.RET]
            )
            if len(gg) < 10:
                continue
            s = ra.score(gg, f"{name} | {basis}", n_boot=2000)
            rows.append(
                {
                    "book": name,
                    "basis": basis,
                    "n": s.n,
                    "mean": s.mean,
                    "sharpe": s.sharpe,
                    "hit": s.hit,
                    "ci_lo": s.ci_lo,
                    "ci_hi": s.ci_hi,
                    "median_width_entry": float(g["width_entry"].median()),
                    "median_width_exit": float(g["width_exit"].median()),
                }
            )
    tbl = pd.DataFrame(rows)
    ra.show(
        tbl,
        [
            "book",
            "basis",
            "n",
            "mean",
            "sharpe",
            "hit",
            "ci_lo",
            "ci_hi",
            "median_width_entry",
            "median_width_exit",
        ],
    )
    ra.write(tbl, "execution_analysis.csv")

    sel_w = selection(d)["width_entry"].median()
    all_w = d["width_entry"].median()
    print(
        f"\n  selected population entry width {sel_w:.4f} vs unconditional {all_w:.4f} "
        f"({sel_w / all_w - 1:+.1%})"
    )
    exec_top = tbl[(tbl["book"].str.contains("top 20")) & (tbl["basis"] == "quoted bid/ask taken")]
    if not exec_top.empty:
        r = exec_top.iloc[0]
        print(
            f"  taking both quoted sides, the selected book is mean {r['mean']:+.5f}, "
            f"Sharpe {r['sharpe']:+.4f}, CI [{r['ci_lo']:+.4f}, {r['ci_hi']:+.4f}]"
        )
    return tbl


def main() -> None:
    panel = load_panel()
    disc = panel[panel["block"] == DISCOVERY].reset_index(drop=True)
    print(
        f"discovery block: {len(disc)} events; signal defined on " f"{disc[SIGNAL].notna().sum()}"
    )

    p4 = phase4(disc)
    p5 = phase5(disc)
    phase7(disc)
    phase8(disc)
    phase9(disc)

    top = p5[(p5["scheme"] == "quintile")].sort_values("bin").iloc[-1]
    bot = p5[(p5["scheme"] == "quintile")].sort_values("bin").iloc[0]
    ra.ledger_append(
        hypothesis_id="H04",
        hypothesis="The P&L of the jump_richness selection is carried by volatility repricing "
        "rather than by cheaper contracts or avoided gaps",
        mechanism="Overpriced event premium should show up as residual value at exit, not as "
        "a smaller realised move",
        variables="credit_mkt, intr_exit, exit_mkt, cost_frozen",
        sample=f"{DISCOVERY}",
        parameters=f"top {1 - CUT:.0%} on {SIGNAL}",
        conceived="before (planned as Phase 4)",
        result="; ".join(
            f"{c} {p4.loc[p4['label'].str.contains('top'), c].iloc[0]:+.5f}"
            for c in [
                "premium_collected",
                "gap_cost_intrinsic",
                "residual_value_at_exit",
                "cost_frozen",
            ]
        ),
        inference="see findings",
        verdict="continue",
        reason="Decomposition is descriptive of the selected book",
        next="H05: test the opposite tail",
    )
    ra.ledger_append(
        hypothesis_id="H05",
        hypothesis="Low jump_richness behaves oppositely, making this one pricing relationship "
        "rather than an isolated profitable tail",
        mechanism="If the market misprices the event jump relative to the name's own history, "
        "the error should have both signs",
        variables=SIGNAL,
        sample=f"{DISCOVERY}",
        parameters="quintile and decile sorts, global bins",
        conceived="before (planned as Phase 5)",
        result=f"bottom quintile mean {bot['mean']:+.5f} (Sharpe {bot['sharpe']:+.4f}); "
        f"top quintile mean {top['mean']:+.5f} (Sharpe {top['sharpe']:+.4f})",
        inference="see findings",
        verdict="continue",
        reason="Sign reversal at the low end is the strong form of the evidence",
        next="H06: neutralise mechanical confounds",
    )
    print("\nphases 4, 5, 7, 8, 9 complete.")


if __name__ == "__main__":
    main()
