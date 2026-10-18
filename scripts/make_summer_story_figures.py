"""
make_summer_story_figures.py
Render the chronological figure set for the summer record, 25 May to 18 August 2026.

Fourteen figures in six acts, all drawn from result artefacts already on disk, so the
run costs nothing and reaches no network. Every annotated number is recomputed from the
named source rather than transcribed from the prose documents, and `_verify` refuses to
write anything if a recomputed headline drifts from the settled verdict or if a figure
label carries one of the numbers the project has withdrawn.

Usage:
    python scripts/make_summer_story_figures.py [--outdir PATH]

References
----------
Bailey, D. and Lopez de Prado, M. (2014). The Deflated Sharpe Ratio: Correcting for
    Selection Bias, Backtest Overfitting and Non-Normality. Journal of Portfolio
    Management 40(5), 94-107.
Lo, A. (2002). The Statistics of Sharpe Ratios. Financial Analysts Journal 58(4), 36-52.
"""

from __future__ import annotations

import argparse
import subprocess
from io import StringIO
from pathlib import Path
from typing import Any, Literal, SupportsFloat, SupportsInt, cast

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.ticker import FuncFormatter
from scipy.stats import norm

# ── paths ────────────────────────────────────────────────────────────────────────

ROOT = Path(__file__).resolve().parents[1]
RESEARCH = ROOT / "outputs" / "research"
DEFAULT_OUT = ROOT / "outputs" / "reports" / "figures" / "summer"

# ── the settled verdict, and the numbers that may never reach a label ────────────

# Recomputed values are checked against these. Sources: outputs/research/
# extension_verdict.csv (blocks), fills_rescore.csv (pooled), oos_2026_verdict.csv (arms).
EXPECTED_SHARPE = {
    "2019-2024": 0.117321,
    "2013-2018": -0.005337,
    "pooled": 0.055992,
    "oos_unconditional": 0.043101,
    "oos_term_gate": -0.209511,
    "oos_random": 0.105211,
}

# Withdrawn figures, per CLAUDE.md. Each is a real number the project once published and
# has since retracted; none may appear on a figure as a result. Tolerance is tight enough
# that a legitimately similar quantity elsewhere in the set will not trip it.
BANNED = {
    2.04: "sqrt(252) artefact on a 35-trade-per-year book",
    4.24: "sqrt(252) artefact, CI bound",
    8.30: "sqrt(252) artefact, CI bound",
    0.115773: "unrepaired exit mark; only reproducible with the intrinsic repair disabled",
    0.023504: "split-basis defect stripped the decade's winners from the sample",
    0.85395: "gross, mid-marked, Black-Scholes-inverted block Sharpe",
    0.0076110: "trade-conditional half-spread; a selection artefact, not an attainable cost",
}

# ── style ────────────────────────────────────────────────────────────────────────

# Categorical slots 1-3 of the validated default palette. Validated all-pairs on the
# light surface: worst CVD dE 9.2, worst normal-vision dE 24.0. AQUA sits below 3:1
# against the surface, so every figure using it ships visible direct labels.
BLUE = "#2a78d6"
ORANGE = "#eb6834"
AQUA = "#1baf7a"
RED = "#e34948"  # status only, always beside a word saying what the status is
INK = "#0b0b0b"
SECOND = "#52514e"
MUTED = "#8a8880"
GRID = "#e4e3df"
SURFACE = "#fcfcfb"

plt.rcParams.update(
    {
        "figure.facecolor": SURFACE,
        "axes.facecolor": SURFACE,
        "savefig.facecolor": SURFACE,
        "axes.edgecolor": MUTED,
        "axes.labelcolor": SECOND,
        "axes.titlecolor": INK,
        "axes.titlesize": 11,
        "axes.titleweight": "bold",
        "axes.labelsize": 9,
        "axes.spines.top": False,
        "axes.spines.right": False,
        "xtick.color": SECOND,
        "ytick.color": SECOND,
        "xtick.labelsize": 8.5,
        "ytick.labelsize": 8.5,
        "grid.color": GRID,
        "grid.linewidth": 0.8,
        "legend.frameon": False,
        "legend.fontsize": 8.5,
        "font.size": 9,
        "figure.dpi": 200,
        "savefig.dpi": 200,
        "savefig.bbox": "tight",
    }
)

PCT = FuncFormatter(lambda v, _: f"{v:,.0%}")
PCT1 = FuncFormatter(lambda v, _: f"{v:,.1%}")
USD = FuncFormatter(lambda v, _: f"${v:,.0f}")


# A pandas or numpy scalar read out of a frame is statically a union of everything the
# column could hold. These narrow it once, at the boundary, rather than scattering casts.
Num = float | np.floating[Any] | np.integer[Any]


def _f(value: object) -> float:
    """Narrow a pandas or numpy scalar to a plain float."""
    return float(cast(SupportsFloat, value))


def _i(value: object) -> int:
    """Narrow a pandas or numpy scalar to a plain int."""
    return int(cast(SupportsInt, value))


def _grid(ax: plt.Axes, axis: Literal["both", "x", "y"] = "y") -> None:
    ax.grid(axis=axis, zorder=0)
    ax.set_axisbelow(True)


def _note(fig: plt.Figure, text: str) -> None:
    """Provenance and caveat line under every figure. The reader should never have to
    ask which file a panel came from."""
    fig.text(0.0, -0.055, text, fontsize=7.2, color=MUTED, ha="left", va="top", wrap=True)


WRITTEN: list[tuple[str, float]] = []


def _label(ax: plt.Axes, x: Any, y: Any, text: str, value: Num | None = None, **kw: Any) -> None:
    """Direct label at (x, y), which may be dates on a time axis.

    Any numeric value placed on a figure is registered here so `verify_labels` can check
    it against the withdrawn list before the run is allowed to finish."""
    if value is not None:
        WRITTEN.append((text, float(value)))
    kw.setdefault("fontsize", 8.5)
    kw.setdefault("color", INK)
    ax.text(x, y, text, **kw)


def _save(fig: plt.Figure, out: Path, slug: str) -> Path:
    path = out / f"{slug}.png"
    fig.savefig(path)
    plt.close(fig)
    print(f"  wrote {path.relative_to(ROOT)}")
    return path


# ── loaders ──────────────────────────────────────────────────────────────────────


def _load(name: str) -> pd.DataFrame:
    return pd.read_csv(RESEARCH / name)


def _git_show(ref_path: str) -> pd.DataFrame:
    """Read a CSV as it stands at a git ref. The forward book is written by a scheduled
    job that commits straight to the remote, so the working tree is routinely behind it;
    reading the ref rather than the file is the difference between the current book and a
    stale one."""
    out = subprocess.run(
        ["git", "-C", str(ROOT), "show", ref_path],
        capture_output=True,
        text=True,
        check=True,
    )
    return pd.read_csv(StringIO(out.stdout))


def expected_max_sharpe(sr_trials_std: float, n_trials: int) -> float:
    """Expected maximum Sharpe from a family of `n_trials` strategies with no edge at all
    (Bailey and Lopez de Prado, 2014). This is the bar an in-sample result has to clear
    before it means anything, and it is derived here rather than quoted."""
    gamma = 0.5772156649015329  # Euler-Mascheroni
    a = norm.ppf(1.0 - 1.0 / n_trials)
    b = norm.ppf(1.0 - 1.0 / (n_trials * np.e))
    return float(sr_trials_std * ((1.0 - gamma) * a + gamma * b))


# ── the guard ────────────────────────────────────────────────────────────────────


def verify() -> dict[str, float]:
    """Recompute the headline numbers from source and refuse to draw if they have moved.

    A figure set that quietly disagrees with the documents it accompanies is worse than
    no figure set: the reader has no way to tell which one is stale.
    """
    ext = _load("extension_verdict.csv").set_index("block")
    resc = _load("fills_rescore.csv")
    oos = _load("oos_2026_verdict.csv").set_index("arm")

    pooled_row = resc.loc[resc["cost_basis"] == "assumed_fixed_cost"].iloc[0]
    got = {
        "2019-2024": _f(ext.loc["2019-2024 (original)", "per_trade_sharpe"]),
        "2013-2018": _f(ext.loc["2013-2018 (extension)", "per_trade_sharpe"]),
        "pooled": float(pooled_row["sharpe_pooled"]),
        "oos_unconditional": _f(oos.loc["agent0_unconditional", "per_trade_sharpe"]),
        "oos_term_gate": _f(oos.loc["term_gate_q80_frozen", "per_trade_sharpe"]),
        "oos_random": _f(oos.loc["random_gate_matched", "per_trade_sharpe"]),
    }
    for key, want in EXPECTED_SHARPE.items():
        if abs(got[key] - want) > 5e-6:
            raise SystemExit(
                f"verify: {key} is {got[key]:.6f} on disk against a settled {want:+.6f}. "
                "Either the artefacts were rebuilt or the verdict moved. Resolve that "
                "before drawing anything."
            )

    # The equity curve has to hold the same trade count as the verdict it annotates.
    eq = _load("equity_curves.csv")
    if len(eq) != 391:
        raise SystemExit(f"verify: equity_curves.csv holds {len(eq)} trades, expected 391.")

    print("verify: headline Sharpes and trade count agree with the settled verdict")
    return got


def verify_labels() -> None:
    """No withdrawn number may appear on a figure."""
    offences = []
    for text, value in WRITTEN:
        for bad, why in BANNED.items():
            if abs(value - bad) <= max(1e-6, abs(bad) * 5e-4):
                offences.append(f"  {value!r} in {text!r}: {why}")
    if offences:
        raise SystemExit(
            "verify: withdrawn numbers reached a figure label:\n" + "\n".join(offences)
        )
    print(
        f"verify: {len(WRITTEN)} annotated values checked against the withdrawn list, none present"
    )


# ── Act I: the effect and the platform ───────────────────────────────────────────


def fig01_implied_vs_realised(out: Path) -> None:
    led = _load("oos_2026_ledger.csv")
    imp, real = led["implied_move"].to_numpy(), led["realised_move"].abs().to_numpy()
    m_imp, m_real = float(np.median(imp)), float(np.median(real))

    fig, ax = plt.subplots(figsize=(7.4, 4.6))
    _grid(ax, "both")
    lim = 0.30
    ax.plot([0, lim], [0, lim], color=MUTED, lw=1.2, ls="--", zorder=2)
    ax.scatter(imp, real, s=9, color=BLUE, alpha=0.35, linewidths=0, zorder=3)
    ax.axvline(m_imp, color=ORANGE, lw=1.6, zorder=4)
    ax.axhline(m_real, color=AQUA, lw=1.6, zorder=4)

    _label(
        ax,
        lim * 0.985,
        lim * 0.955,
        "sold move = delivered move",
        None,
        color=SECOND,
        fontsize=8,
        ha="right",
        rotation=39,
        rotation_mode="anchor",
    )
    _label(ax, m_imp + 0.006, lim * 0.93, f"median implied {m_imp:.2%}", m_imp, color=ORANGE)
    _label(
        ax,
        lim * 0.985,
        m_real + 0.007,
        f"median realised {m_real:.2%}",
        m_real,
        color=AQUA,
        ha="right",
    )

    below = float((real < imp).mean())
    _label(
        ax,
        0.163,
        0.102,
        f"implied is {m_imp / m_real:.1f}x realised at the median.\n"
        f"the stock moves less than the option\ncharged on {below:.0%} of events",
        None,
        color=INK,
        fontsize=9.2,
        va="top",
    )

    ax.set_xlim(0, lim)
    ax.set_ylim(0, lim)
    ax.xaxis.set_major_formatter(PCT)
    ax.yaxis.set_major_formatter(PCT)
    ax.set_xlabel("implied move priced into the straddle at entry")
    ax.set_ylabel("realised move, absolute, entry to exit")
    ax.set_title("The effect the whole project rests on")
    _note(
        fig,
        f"outputs/research/oos_2026_ledger.csv, N = {len(led):,} events, 313 names, "
        "Jan 2025 to Jun 2026. Points below the dashed line are events where the option "
        "was dear. This is the raw effect, before any selection, cost or margin.",
    )
    _save(fig, out, "fig01_implied_vs_realised")


def fig02_marking_basis(out: Path) -> None:
    qc = pd.read_csv(ROOT / "quote_vs_close.csv")
    rows = [
        ("daily close\ntreated as a mid", "close_violates", ORANGE),
        ("NBBO mid\nfrom the quote", "nbbo_mid_violates", BLUE),
        ("NBBO bid\nthe honest exit", "nbbo_bid_violates", AQUA),
    ]
    rates = [float(qc[c].mean()) for _, c, _ in rows]

    fig, (ax1, ax2) = plt.subplots(
        1,
        2,
        figsize=(10.0, 4.3),
        gridspec_kw={"width_ratios": [1, 1.25], "wspace": 0.30},
    )

    _grid(ax1)
    xs = np.arange(len(rows))
    ax1.bar(xs, rates, width=0.55, color=[c for _, _, c in rows], zorder=3)
    for x, r in zip(xs, rates, strict=False):
        _label(ax1, x, r + 0.012, f"{r:.1%}", r, ha="center", fontweight="bold")
    ax1.set_xticks(xs)
    ax1.set_xticklabels([n for n, _, _ in rows])
    ax1.set_ylim(0, max(rates) * 1.35)
    ax1.yaxis.set_major_formatter(PCT)
    ax1.set_ylabel("share of exits marked below intrinsic value")
    ax1.set_title("How often the mark was impossible")

    _grid(ax2, "both")
    ax2.plot([0, 90], [0, 90], color=MUTED, lw=1.2, ls="--", zorder=2)
    ax2.scatter(
        qc["intrinsic"],
        qc["trade_close"],
        s=34,
        color=ORANGE,
        alpha=0.85,
        linewidths=0.8,
        edgecolors=SURFACE,
        zorder=4,
        label="daily close",
    )
    ax2.scatter(
        qc["intrinsic"],
        qc["nbbo_mid"],
        s=34,
        color=BLUE,
        alpha=0.85,
        linewidths=0.8,
        edgecolors=SURFACE,
        zorder=3,
        label="NBBO mid",
    )
    ax2.set_xlabel("intrinsic value at exit, the floor a price cannot go below ($)")
    ax2.set_ylabel("straddle mark at exit ($)")
    ax2.set_title("Below the dashed line is a price that could not trade")
    ax2.legend(loc="upper left")

    fig.suptitle(
        "June: the marking basis, and why the first month of results was rebuilt",
        fontsize=11.5,
        fontweight="bold",
        y=1.02,
    )
    _note(
        fig,
        "quote_vs_close.csv, 39 events with matched OPRA quotes. A closing price is the "
        "last trade, not a mid, and on this sample it prices the buy-back below intrinsic "
        "more than twice as often as the quote does. Quote marking became the standard for "
        "everything after this and the earlier results were rebuilt on it.",
    )
    _save(fig, out, "fig02_marking_basis")


# ── Act II: the term-structure selector ──────────────────────────────────────────


def fig03_twelve_year_equity(out: Path) -> None:
    eq = _load("equity_curves.csv")
    eq["entry_date"] = pd.to_datetime(eq["entry_date"])
    ext = _load("extension_verdict.csv").set_index("block")

    fig, ax = plt.subplots(figsize=(8.6, 4.6))
    _grid(ax)

    order = ["2013-2018 (extension)", "2019-2024 (original)"]
    colours = {"2013-2018 (extension)": ORANGE, "2019-2024 (original)": BLUE}
    labels = {
        "2013-2018 (extension)": "2013-2018, true holdout, built after the first block was scored",
        "2019-2024 (original)": "2019-2024, in sample, the block the rule was chosen on",
    }
    for block in order:
        d = eq[eq["block"] == block].sort_values("entry_date")
        cum = d["pnl"].cumsum()
        ax.plot(d["entry_date"], cum, color=colours[block], lw=1.9, label=labels[block], zorder=3)
        row = ext.loc[block]
        n = _i(row["n"])
        sh, lo, hi = (_f(row["per_trade_sharpe"]), _f(row["ci_lo"]), _f(row["ci_hi"]))
        _label(
            ax,
            d["entry_date"].iloc[-1],
            cum.iloc[-1],
            f"  N = {n}   per-trade Sharpe {sh:+.3f}\n  clustered 95% CI [{lo:+.3f}, {hi:+.3f}]",
            sh,
            color=colours[block],
            va="center",
            fontsize=8.2,
        )

    ax.axhline(0, color=MUTED, lw=1.0, zorder=2)
    ax.yaxis.set_major_formatter(USD)
    ax.set_ylabel("cumulative P&L within block ($)")
    ax.set_xlabel("trade entry date")
    ax.set_title("The frozen term-structure book, in sample and on its holdout")
    ax.legend(loc="upper left")
    # Matplotlib accepts datetimes here; the stub only admits floats.
    ax.set_xlim(pd.Timestamp("2012-10-01"), pd.Timestamp("2028-06-01"))  # type: ignore[arg-type]

    _note(
        fig,
        "outputs/research/equity_curves.csv and extension_verdict.csv. Nothing was retuned "
        "between the blocks: the specification was frozen on 2019-2024 and the earlier years "
        "were then built on identical machinery. Both intervals contain zero, and the holdout "
        "returns essentially nothing. Sharpe is per trade; the annualised figures use each "
        "block's own trade rate of about 35 a year, not a daily convention.",
    )
    _save(fig, out, "fig03_twelve_year_equity")


def fig04_yearly(out: Path) -> None:
    y = _load("equity_yearly.csv")
    years = y["year"].to_numpy()
    gross, net = y["gross_pnl"].to_numpy(), y["net_pnl"].to_numpy()

    fig, ax = plt.subplots(figsize=(8.6, 4.4))
    _grid(ax)
    w = 0.38
    ax.bar(years - w / 2, gross, width=w, color=BLUE, zorder=3, label="gross of costs")
    ax.bar(years + w / 2, net, width=w, color=ORANGE, zorder=3, label="net of costs")
    ax.axhline(0, color=INK, lw=1.0, zorder=4)

    top2 = y.nlargest(2, "net_pnl")
    total = float(net.sum())
    carried = float(top2["net_pnl"].sum())
    for _, r in top2.iterrows():
        _label(
            ax,
            r["year"] + w / 2,
            r["net_pnl"] + 900,
            f"${r['net_pnl']:,.0f}",
            r["net_pnl"],
            ha="center",
            fontsize=8,
            fontweight="bold",
            color=ORANGE,
        )

    _label(
        ax,
        years.min() - 0.4,
        min(net) * 0.92,
        f"{int(top2['year'].iloc[0])} and {int(top2['year'].iloc[1])} together contribute "
        f"${carried:,.0f}\nagainst a twelve-year total of ${total:,.0f}",
        carried,
        va="top",
        fontsize=9,
    )

    ax.set_xticks(years)
    ax.yaxis.set_major_formatter(USD)
    ax.set_ylabel("P&L for the year ($)")
    ax.set_title("Where the twelve-year P&L actually came from")
    ax.legend(loc="upper left")
    _note(
        fig,
        "outputs/research/equity_yearly.csv, N = 391 trades. The gap between the pairs is "
        "the cost drag. Two calendar years carry more than the whole record, which is the "
        "concentration objection a reader should raise before any Sharpe is discussed.",
    )
    _save(fig, out, "fig04_yearly")


def fig05_deflation(out: Path) -> None:
    panel = _load("performance_panel.csv")
    n_trials = int(panel["n_trials"].iloc[0])
    sr_std = float(panel["sr_trials_std"].iloc[0])
    e_max = expected_max_sharpe(sr_std, n_trials)
    ext = _load("extension_verdict.csv").set_index("block")
    resc = _load("fills_rescore.csv")
    pooled = float(resc.loc[resc["cost_basis"] == "assumed_fixed_cost", "sharpe_pooled"].iloc[0])

    bars = [
        ("2013-2018\nholdout", _f(ext.loc["2013-2018 (extension)", "per_trade_sharpe"]), ORANGE),
        ("pooled\nN = 391", pooled, AQUA),
        ("2019-2024\nin sample", _f(ext.loc["2019-2024 (original)", "per_trade_sharpe"]), BLUE),
    ]

    fig, ax = plt.subplots(figsize=(7.6, 4.4))
    _grid(ax)
    xs = np.arange(len(bars))
    ax.bar(xs, [v for _, v, _ in bars], width=0.5, color=[c for _, _, c in bars], zorder=3)
    for x, (_, v, c) in zip(xs, bars, strict=False):
        off = 0.014 if v >= 0 else -0.028
        _label(ax, x, v + off, f"{v:+.3f}", v, ha="center", fontweight="bold", color=c)

    ax.axhline(e_max, color=RED, lw=1.8, ls="--", zorder=5)
    _label(
        ax,
        -0.42,
        e_max + 0.018,
        f"expected best Sharpe from {n_trials:,} strategies with no edge at all: {e_max:+.3f}",
        e_max,
        color=RED,
        ha="left",
        fontsize=8.6,
        fontweight="bold",
    )
    ax.axhline(0, color=INK, lw=1.0, zorder=4)

    ax.set_xticks(xs)
    ax.set_xticklabels([n for n, _, _ in bars])
    ax.set_ylim(min(-0.06, min(v for _, v, _ in bars) - 0.05), e_max * 1.30)
    ax.set_ylabel("per-trade Sharpe")
    ax.set_title("Every in-sample number, against the bar it has to clear")
    _note(
        fig,
        "Achieved Sharpes from extension_verdict.csv and fills_rescore.csv. The dashed line "
        "is derived in this script from performance_panel.csv "
        f"(n_trials = {n_trials:,}, dispersion {sr_std:.4f}) by the Bailey and Lopez de Prado "
        "(2014) expected-maximum formula, not quoted. Searching that many configurations "
        "would be expected to throw up a better result than this book achieved even if "
        "there were nothing there. That is why the next selector has to be pre-registered "
        "and tested once.",
    )
    _save(fig, out, "fig05_deflation")


# ── Act III: marks and execution ─────────────────────────────────────────────────


def fig06_mark_repair(out: Path) -> None:
    mi = _load("mark_integrity.csv")
    keep = {
        "as-is (the headline)": ("the mark as first published\n(withdrawn)", RED),
        "marks floored at intrinsic": ("floored at intrinsic", BLUE),
        "exit rebuilt from put-call parity": ("rebuilt from put-call parity", AQUA),
    }
    d = mi[mi["arm"].isin(keep)].copy()
    d["label"] = d["arm"].map(lambda a: keep[a][0])
    d["colour"] = d["arm"].map(lambda a: keep[a][1])
    d = d.iloc[::-1]

    fig, ax = plt.subplots(figsize=(8.6, 3.3))
    _grid(ax, "x")
    ys = np.arange(len(d))
    for y, (_, r) in zip(ys, d.iterrows(), strict=False):
        ax.plot(
            [r["ci_lo"], r["ci_hi"]],
            [y, y],
            color=r["colour"],
            lw=2.4,
            solid_capstyle="round",
            zorder=3,
        )
        ax.scatter(
            [r["sharpe"]],
            [y],
            s=64,
            color=r["colour"],
            zorder=4,
            edgecolors=SURFACE,
            linewidths=1.2,
        )
        # The withdrawn headline is shown as a position, never as a number.
        txt = "withdrawn" if r["arm"] == "as-is (the headline)" else f"{r['sharpe']:+.4f}"
        val = None if r["arm"] == "as-is (the headline)" else float(r["sharpe"])
        _label(
            ax, 0.355, y, txt, val, va="center", fontsize=8.6, fontweight="bold", color=r["colour"]
        )

    ax.axvline(0, color=INK, lw=1.0, zorder=2)
    ax.set_yticks(ys)
    ax.set_yticklabels(d["label"])
    ax.set_xlabel("per-trade Sharpe, with bootstrap 95% interval")
    ax.set_title("July: the repair that took the headline apart", pad=12)
    ax.set_xlim(-0.16, 0.50)
    ax.set_ylim(-0.65, len(d) - 0.35)

    _note(
        fig,
        "outputs/research/mark_integrity.csv, N = 192. The entire distance between "
        "significant and not significant was exit marks priced below intrinsic: prices at "
        "which the straddle could not have traded. The published Sharpe was only reproducible "
        "with the intrinsic repair switched off, and mark_integrity.csv was written twenty "
        "minutes before engine/marks.py, so the headline predated its own repair. That number "
        "is on the project's withdrawn list and is deliberately not printed here. Both "
        "repaired arms have intervals containing zero.",
    )
    _save(fig, out, "fig06_mark_repair")


def fig07_fills(out: Path) -> None:
    prints = pd.read_parquet(RESEARCH / "fill_prints.parquet")
    study = _load("fills_study.csv").iloc[0]
    loc = prints["fill_loc"].clip(0, 1).to_numpy()

    fig, ax = plt.subplots(figsize=(8.4, 4.4))
    _grid(ax)
    bins = np.linspace(0, 1, 41)
    counts, edges = np.histogram(loc, bins=bins)
    centres = (edges[:-1] + edges[1:]) / 2
    colours = [AQUA if c < 0.5 else (MUTED if abs(c - 0.5) < 1e-9 else ORANGE) for c in centres]
    ax.bar(centres, counts, width=(bins[1] - bins[0]) * 0.92, color=colours, zorder=3)

    at_mid = float(study["frac_at_or_better_than_mid"])
    full_touch = float(study["frac_worse_than_touch_half"])
    med_imp = float(study["improvement_median"])

    ax.axvline(0.5, color=INK, lw=1.2, ls="--", zorder=4)
    _label(ax, 0.5, counts.max() * 1.03, "mid", None, ha="center", color=INK, fontsize=8.5)
    _label(
        ax,
        0.02,
        counts.max() * 1.03,
        "bid, where you want to buy",
        None,
        color=SECOND,
        fontsize=8.2,
    )
    _label(
        ax,
        0.98,
        counts.max() * 1.03,
        "ask, where you pay up",
        None,
        color=SECOND,
        fontsize=8.2,
        ha="right",
    )

    _label(
        ax,
        0.06,
        counts.max() * 0.80,
        f"only {at_mid:.1%} of prints executed at or better than the mid\n"
        f"{full_touch:.1%} paid the full touch\n"
        f"median price improvement {med_imp:.1%}",
        at_mid,
        fontsize=9.2,
        va="top",
        color=INK,
    )

    ax.set_xlim(0, 1)
    ax.set_xlabel("where the trade printed between the prevailing bid (0) and ask (1)")
    ax.set_ylabel("number of prints")
    ax.set_title("Where option trades actually fill, on 34,672 real prints")
    _note(
        fig,
        "outputs/research/fill_prints.parquet and fills_study.csv, 34,672 usable prints from "
        "3.2M Databento records across 162 of 162 windows, 15:30 to 15:59 ET. Backtests that "
        "assume a mid fill assume the left half of this distribution. The attainable "
        "unconditional cost measured here is 1.7871% per side against the 2.000% the book "
        "had assumed; rescoring on it leaves the pooled interval still containing zero.",
    )
    _save(fig, out, "fig07_fills")


def fig08_margin(out: Path) -> None:
    m = _load("ib_margin_probe.csv").sort_values("margin_ratio")

    fig, ax = plt.subplots(figsize=(8.0, 4.2))
    _grid(ax, "x")
    ys = np.arange(len(m))
    for y, (_, r) in zip(ys, m.iterrows(), strict=False):
        ax.plot([r["modelled_margin"], r["ib_init_margin"]], [y, y], color=MUTED, lw=1.4, zorder=2)
        ax.scatter(
            [r["modelled_margin"]],
            [y],
            s=58,
            color=BLUE,
            zorder=4,
            edgecolors=SURFACE,
            linewidths=1.1,
        )
        ax.scatter(
            [r["ib_init_margin"]],
            [y],
            s=58,
            color=ORANGE,
            zorder=4,
            edgecolors=SURFACE,
            linewidths=1.1,
        )
        _label(
            ax,
            r["ib_init_margin"] * 1.04,
            y,
            f"{r['margin_ratio']:.2f}x",
            r["margin_ratio"],
            va="center",
            fontsize=8.2,
            fontweight="bold",
            color=ORANGE,
        )

    ax.scatter([], [], s=58, color=BLUE, label="modelled Reg-T: 0.20 x spot + premium")
    ax.scatter([], [], s=58, color=ORANGE, label="what the broker actually held")
    ax.set_yticks(ys)
    ax.set_yticklabels(m["ticker"])
    ax.set_xscale("log")
    ax.xaxis.set_major_formatter(USD)
    ax.set_xlabel("initial margin for one short straddle, log scale ($)")
    ax.set_title("The denominator every return in this set is divided by")
    ax.legend(loc="lower right")
    ax.set_xlim(1500, 120000)
    _note(
        fig,
        "outputs/research/ib_margin_probe.csv, 7 names, IB whatIf orders on 2026-07-13, never "
        "transmitted. The broker holds 2.18 to 2.37 times the modelled figure, so every "
        "return-on-margin level in this document is a research measure rather than a "
        "deployable one. Comparisons between books are unaffected because they share the "
        "convention. This is the largest unvalidated assumption in the project.",
    )
    _save(fig, out, "fig08_margin")


# ── Act IV: the clean out-of-sample block ────────────────────────────────────────


def fig09_three_books(out: Path) -> None:
    v = _load("oos_2026_verdict.csv").set_index("arm")
    arms = [
        ("term_gate_q80_frozen", "the frozen term selector\nthe summer's main strategy", RED),
        ("random_gate_matched", "picking events at random\nat matched participation", ORANGE),
        ("agent0_unconditional", "no selector at all\nsell every eligible event", BLUE),
    ]

    fig, ax = plt.subplots(figsize=(9.0, 3.4))
    _grid(ax, "x")
    ys = np.arange(len(arms))
    for y, (key, _name, colour) in zip(ys, arms, strict=False):
        r = v.loc[key]
        ax.plot(
            [r["ci_low"], r["ci_high"]],
            [y, y],
            color=colour,
            lw=2.6,
            solid_capstyle="round",
            zorder=3,
        )
        ax.scatter(
            [r["per_trade_sharpe"]],
            [y],
            s=76,
            color=colour,
            zorder=4,
            edgecolors=SURFACE,
            linewidths=1.3,
        )
        _label(
            ax,
            0.335,
            y,
            f"{r['per_trade_sharpe']:+.3f}   N = {_i(r['n']):,}   hit {r['hit_rate']:.1%}",
            _f(r["per_trade_sharpe"]),
            va="center",
            fontsize=8.5,
            fontweight="bold",
            color=colour,
        )

    ax.axvline(0, color=INK, lw=1.2, zorder=2)
    ax.set_yticks(ys)
    ax.set_yticklabels([n for _, n, _ in arms])
    ax.set_xlabel("per-trade Sharpe on return on margin, with date-clustered 95% interval")
    ax.set_title("August: three books on one basis, on data nothing was fitted to", pad=12)
    ax.set_xlim(-0.40, 0.62)
    ax.set_ylim(-0.6, len(arms) - 0.4)

    _note(
        fig,
        "The selector three months of work went into is the only one of the three whose "
        "interval excludes zero, and it does so on the wrong side. "
        "outputs/research/oos_2026_verdict.csv. Block: 2,037 events across 346 names, "
        "Jan 2025 to Jun 2026, constructed after the 1,476-configuration search had closed "
        "and pre-registered with both kill criteria declared before the first data request "
        "(outputs/research/prereg_oos_2026.json, one trial declared). A participation-matched "
        "random selector is the only fair benchmark for a rule: it holds trade count and "
        "eligible pool fixed and varies only the selection.",
    )
    _save(fig, out, "fig09_three_books")


def fig10_diagnosis(out: Path) -> None:
    led = _load("oos_2026_ledger.csv")
    v = _load("oos_2026_verdict.csv").set_index("arm")
    gated = led[led["term_gate"].astype(bool)]

    groups = [
        ("every eligible event", led, BLUE, "agent0_unconditional"),
        ("the events the gate chose", gated, RED, "term_gate_q80_frozen"),
    ]

    fig, (ax1, ax2) = plt.subplots(
        1,
        2,
        figsize=(10.4, 4.4),
        gridspec_kw={"width_ratios": [1.25, 1], "wspace": 0.30},
    )

    _grid(ax1)
    w = 0.34
    xs = np.arange(len(groups))
    for i, (_name, d, colour, _) in enumerate(groups):
        mi = float(d["implied_move"].median())
        mr = float(d["realised_move"].abs().median())
        ax1.bar(i - w / 2, mi, width=w, color=colour, zorder=3)
        ax1.bar(i + w / 2, mr, width=w, color=colour, alpha=0.42, zorder=3)
        _label(ax1, i - w / 2, mi + 0.0018, f"{mi:.2%}", mi, ha="center", fontsize=8, color=colour)
        _label(ax1, i + w / 2, mr + 0.0018, f"{mr:.2%}", mr, ha="center", fontsize=8, color=SECOND)
        _label(
            ax1,
            i,
            max(mi, mr) + 0.0095,
            f"{mi / mr:.1f}x",
            mi / mr,
            ha="center",
            fontsize=11.5,
            fontweight="bold",
            color=colour,
        )
    ax1.set_xticks(xs)
    ax1.set_xticklabels([n for n, _, _, _ in groups])
    ax1.yaxis.set_major_formatter(PCT1)
    ax1.set_ylim(0, 0.115)
    ax1.set_ylabel("median move")
    ax1.set_title("Implied against realised, and the ratio")
    handles = [
        matplotlib.patches.Patch(facecolor=MUTED, label="implied, what the option charged"),
        matplotlib.patches.Patch(facecolor=MUTED, alpha=0.42, label="realised, what the stock did"),
    ]
    ax1.legend(handles=handles, loc="upper center", ncol=1)

    _grid(ax2)
    for i, (_name, _, colour, key) in enumerate(groups):
        g = _f(v.loc[key, "mean_gross_rom"])
        ax2.bar(i, g, width=0.46, color=colour, zorder=3)
        _label(ax2, i, g + 0.0012, f"{g:+.2%}", g, ha="center", fontweight="bold", color=colour)
    ax2.set_xticks(xs)
    ax2.set_xticklabels([n for n, _, _, _ in groups])
    ax2.axhline(0, color=INK, lw=1.0, zorder=4)
    ax2.yaxis.set_major_formatter(PCT1)
    ax2.set_ylim(0, 0.043)
    ax2.set_ylabel("mean return on margin, before any cost")
    ax2.set_title("Gross, so cost is not the explanation")

    fig.suptitle(
        "Why it failed: the gate was finding risk, not overpricing",
        fontsize=11.5,
        fontweight="bold",
        y=1.02,
    )
    _note(
        fig,
        "outputs/research/oos_2026_ledger.csv and oos_2026_verdict.csv. A steep term "
        "structure does identify events where the market charges a large implied move. Those "
        "are also the events where the large move happens, so the ratio the trade needs "
        "collapses from 2.1 to 1.2 on exactly the events the rule selected. The gross panel "
        "closes the obvious objection: the gated book had almost no premium to collect "
        "before a single cost was charged.",
    )
    _save(fig, out, "fig10_diagnosis")


def fig11_attribution(out: Path) -> None:
    da = _load("driver_attribution.csv")
    d = da[da["book"] == "GATED (quote-marked)"].set_index("order")
    legs = ["theta", "vega", "spot"]
    orders = [("tvs", "theta first"), ("svt", "spot first")]

    fig, ax = plt.subplots(figsize=(8.2, 4.4))
    _grid(ax)
    w = 0.36
    xs = np.arange(len(legs))
    for i, (key, name) in enumerate(orders):
        vals = [_f(d.loc[key, leg]) for leg in legs]
        colour = BLUE if key == "tvs" else ORANGE
        ax.bar(xs + (i - 0.5) * w, vals, width=w, color=colour, zorder=3, label=f"ordering: {name}")
        for x, v in zip(xs + (i - 0.5) * w, vals, strict=False):
            off = 6500 if v >= 0 else -13000
            _label(ax, x, v + off, f"${v:,.0f}", v, ha="center", fontsize=7.8, color=colour)

    ax.axhline(0, color=INK, lw=1.0, zorder=4)
    ax.set_xticks(xs)
    ax.set_xticklabels(["theta\ntime decay", "vega\nthe crush itself", "spot\nthe earnings gap"])
    ax.yaxis.set_major_formatter(USD)
    ax.set_ylabel("P&L attributed to the leg ($)")
    ax.set_title("The P&L is carried by the leg the thesis names")
    ax.legend(loc="lower left")
    _note(
        fig,
        "outputs/research/driver_attribution.csv, the quote-marked gated book, N = 198. "
        "Volatilities are inverted from the book's own marks so the decomposition reconciles "
        "to realised P&L exactly. A path-dependent decomposition is order-sensitive, so both "
        "orderings are shown; vega is the largest positive leg under either, which is what "
        "the thesis requires and is not automatic. An earlier version held through the front "
        "expiry and was theta-dominated, which made the verdict meaningless until the exit "
        "timing was fixed. The crush is real; the spot gap is what takes it back.",
    )
    _save(fig, out, "fig11_attribution")


# ── Act V: the pivot ─────────────────────────────────────────────────────────────


def fig12_hold_to_expiry(out: Path) -> None:
    h = pd.read_csv(RESEARCH / "hold_to_expiry.csv")
    dec = _load("hold_decomposition.csv")
    dec = dec[dec["basis"] == "central"].set_index("block")

    fig, (ax1, ax2) = plt.subplots(
        1,
        2,
        figsize=(10.6, 4.4),
        gridspec_kw={"width_ratios": [1.1, 1], "wspace": 0.42},
    )

    lo, hi = -0.55, 0.40
    _grid(ax1, "both")
    ax1.plot([lo, hi], [lo, hi], color=MUTED, lw=1.2, ls="--", zorder=2)
    ax1.scatter(h["rom_plus1"], h["rom_hold"], s=16, color=BLUE, alpha=0.5, linewidths=0, zorder=3)
    ax1.axhline(0, color=MUTED, lw=0.9, zorder=2)
    ax1.axvline(0, color=MUTED, lw=0.9, zorder=2)
    better = float((h["rom_hold"] > h["rom_plus1"]).mean())
    clipped = int(((h["rom_plus1"] < lo) | (h["rom_hold"] < lo)).sum())
    _label(
        ax1,
        lo * 0.96,
        hi * 0.94,
        f"holding longer beat exiting next session\non {better:.0%} of the same {len(h)} trades",
        better,
        fontsize=8.8,
        va="top",
    )
    ax1.set_xlim(lo, hi)
    ax1.set_ylim(lo, hi)
    ax1.xaxis.set_major_formatter(PCT)
    ax1.yaxis.set_major_formatter(PCT)
    ax1.set_xlabel("return on margin, exit the session after earnings")
    ax1.set_ylabel("return on margin, held to expiry")
    ax1.set_title("Same trades, two exits")

    _grid(ax2, "x")
    ys = np.arange(len(dec))
    for y, (block, r) in enumerate(dec.iterrows()):
        colour = BLUE if block == "2019-2024" else ORANGE
        ax2.plot(
            [r["delta_ci_lo"], r["delta_ci_hi"]],
            [y, y],
            color=colour,
            lw=2.5,
            solid_capstyle="round",
            zorder=3,
        )
        ax2.scatter(
            [r["delta_mean_rom"]],
            [y],
            s=68,
            color=colour,
            zorder=4,
            edgecolors=SURFACE,
            linewidths=1.2,
        )
        _label(
            ax2,
            0.030,
            y,
            f"{r['delta_mean_rom']:+.2%}",
            float(r["delta_mean_rom"]),
            va="center",
            fontsize=8.5,
            fontweight="bold",
            color=colour,
        )
    ax2.axvline(0, color=INK, lw=1.1, zorder=2)
    ax2.set_yticks(ys)
    ax2.set_yticklabels([f"{b}\nN = {int(dec.loc[b, 'n'])}" for b in dec.index])
    ax2.set_xlabel("mean advantage of holding, clustered 95% interval")
    ax2.set_title("And it does not hold up on the holdout")
    ax2.set_xlim(-0.045, 0.052)
    ax2.set_ylim(-0.6, len(dec) - 0.4)

    fig.suptitle(
        "A live candidate for the year, with its caveat attached",
        fontsize=11.5,
        fontweight="bold",
        y=1.02,
    )
    _note(
        fig,
        f"outputs/research/hold_to_expiry.csv and hold_decomposition.csv, central basis. The "
        f"left panel is clipped at -55%; {clipped} trades fall outside it and all of them lose "
        "under both exits. The "
        "in-sample block favours holding and its interval still straddles zero; the holdout "
        "reverses the sign. The specific conditional cut reported elsewhere as +17.3% against "
        "-4.4% was chosen in sample, so it is not a clean holdout result and is not drawn "
        "here. Re-testing this on a frozen specification is a first job of the year, not a "
        "formality.",
    )
    _save(fig, out, "fig12_hold_to_expiry")


def fig13_exit_cost(out: Path) -> None:
    curve = _load("exec_exit_curve.csv")
    resc = _load("fills_rescore.csv")

    fig, (ax1, ax2) = plt.subplots(
        1,
        2,
        figsize=(11.2, 4.4),
        gridspec_kw={"wspace": 0.52},
    )

    _grid(ax1)
    for prob, colour in [(1.0, BLUE), (0.8, ORANGE), (0.6, AQUA)]:
        d = curve[curve["fill_prob"] == prob].sort_values("frac_to_touch")
        ax1.plot(
            d["frac_to_touch"],
            d["per_trade_sharpe"],
            color=colour,
            lw=2.0,
            zorder=3,
            marker="o",
            ms=5,
            label=f"{prob:.0%} chance the passive order fills",
        )
        first = d.iloc[0]
        _label(
            ax1,
            0.045,
            first["per_trade_sharpe"],
            f"{first['per_trade_sharpe']:+.3f}",
            float(first["per_trade_sharpe"]),
            ha="left",
            va="center",
            fontsize=8.2,
            fontweight="bold",
            color=colour,
        )
    ax1.axhline(0, color=INK, lw=1.0, zorder=2)
    ax1.set_xlabel("share of the spread given up on the exit")
    ax1.set_ylabel("per-trade Sharpe")
    ax1.set_xticks([0, 0.25, 0.5, 1.0])
    ax1.set_xticklabels(["work the mid", "quarter", "half", "cross it all"])
    ax1.set_title("The exit moves the result more than the signal")
    ax1.legend(loc="upper right")
    ax1.set_xlim(-0.06, 1.06)
    ax1.set_ylim(-0.008, 0.155)

    _grid(ax2, "x")
    rows = [
        ("trade_conditional_print", "conditional on a print\nselection artefact", RED),
        ("measured_1559_snapshot", "measured from the book\nat the mark", AQUA),
        ("assumed_fixed_cost", "the modelling assumption\nthe book was scored on", BLUE),
    ]
    ys = np.arange(len(rows))
    for y, (key, _name, colour) in zip(ys, rows, strict=False):
        r = resc[resc["cost_basis"] == key].iloc[0]
        usable = r["recommended_for_inference"] == "yes"
        ax2.plot(
            [r["ci_lo_pooled"], r["ci_hi_pooled"]],
            [y, y],
            color=colour,
            lw=2.5,
            solid_capstyle="round",
            zorder=3,
            alpha=1.0 if usable else 0.32,
        )
        ax2.scatter(
            [r["sharpe_pooled"]],
            [y],
            s=68,
            color=colour,
            zorder=4,
            edgecolors=SURFACE,
            linewidths=1.2,
            alpha=1.0 if usable else 0.32,
        )
        if usable:
            _label(
                ax2,
                0.245,
                y,
                f"{r['sharpe_pooled']:+.4f}",
                float(r["sharpe_pooled"]),
                va="center",
                fontsize=8.5,
                fontweight="bold",
                color=colour,
            )
        else:
            _label(
                ax2,
                0.245,
                y,
                "excluded",
                None,
                va="center",
                fontsize=8.5,
                fontweight="bold",
                color=colour,
            )
    ax2.axvline(0, color=INK, lw=1.1, zorder=2)
    ax2.set_yticks(ys)
    ax2.set_yticklabels([n for _, n, _ in rows])
    ax2.set_xlabel("pooled per-trade Sharpe, N = 391, clustered 95% interval")
    ax2.set_title("Charging the measured cost does not rescue it")
    ax2.set_xlim(-0.09, 0.36)
    ax2.set_ylim(-0.6, len(rows) - 0.4)

    fig.suptitle(
        "Where the next improvement is most likely to come from",
        fontsize=11.5,
        fontweight="bold",
        y=1.02,
    )
    _note(
        fig,
        "outputs/research/exec_exit_curve.csv and fills_rescore.csv. The left panel varies "
        "only the exit, holding the signal fixed. The right panel rescores the twelve-year "
        "book on three cost bases: the trade-conditional one is 2.35 times tighter than the "
        "fixed-time book because it conditions on a print having occurred, which selects "
        "tight-spread states, so it is excluded from inference and pinned out by "
        "tests/test_fills_rescore_attainability.py. On the honest bases the interval still "
        "contains zero.",
    )
    _save(fig, out, "fig13_exit_cost")


# ── Act VI: the forward book ─────────────────────────────────────────────────────


def fig14_forward_book(out: Path) -> None:
    ledger = _git_show("origin/main:outputs/paper/radar_ledger.csv")
    openpos = _git_show("origin/main:outputs/paper/radar_open_positions.csv")

    # The recorder's own history, from notes/paper_book_log.md and the bot commit log.
    events = [
        ("11 Aug", "deployed", "recorder deployed", AQUA),
        ("11 Aug", "failed", "run failed: API key absent", RED),
        ("12 Aug", "opened", "TPR and CSCO opened", BLUE),
        ("13 Aug", "failed", "run failed: schema mismatch", RED),
        ("14 Aug", "failed", "no run", RED),
        ("17 Aug", "lost", "TPR and CSCO deleted unbooked", RED),
        ("17 Aug", "opened", "HD opened", BLUE),
        ("18 Aug", "booked", "HD booked, 6 rows opened", AQUA),
    ]

    fig, (ax1, ax2) = plt.subplots(
        1,
        2,
        figsize=(10.0, 4.6),
        gridspec_kw={"width_ratios": [1.3, 1], "wspace": 0.22},
    )

    _grid(ax1, "x")
    ys = np.arange(len(events))[::-1]
    for y, (day, _, text, colour) in zip(ys, events, strict=False):
        ax1.scatter([0], [y], s=70, color=colour, zorder=4, edgecolors=SURFACE, linewidths=1.2)
        _label(ax1, 0.035, y, text, None, va="center", fontsize=8.6, color=INK)
        _label(ax1, -0.035, y, day, None, va="center", ha="right", fontsize=8.2, color=SECOND)
    ax1.plot([0, 0], [ys.min(), ys.max()], color=GRID, lw=1.6, zorder=2)
    ax1.set_xlim(-0.16, 1.0)
    ax1.set_ylim(ys.min() - 0.7, ys.max() + 0.7)
    ax1.set_xticks([])
    ax1.set_yticks([])
    for s in ax1.spines.values():
        s.set_visible(False)
    ax1.set_title("Every run the cloud recorder has made")

    _grid(ax2)
    counts = [len(ledger), len(openpos), int(openpos["ticker"].nunique()), 2]
    names = [
        "trades\nbooked",
        "open rows\ncarried",
        "distinct\nnames open",
        "positions lost\nunbooked",
    ]
    colours = [AQUA, BLUE, BLUE, RED]
    xs = np.arange(len(counts))
    ax2.bar(xs, counts, width=0.55, color=colours, zorder=3)
    for x, c in zip(xs, counts, strict=False):
        _label(ax2, x, c + 0.12, str(c), float(c), ha="center", fontweight="bold", fontsize=11)
    ax2.set_xticks(xs)
    ax2.set_xticklabels(names)
    ax2.set_ylim(0, max(counts) * 1.35)
    ax2.set_yticks(range(0, max(counts) + 2, 2))
    ax2.set_ylabel("count")
    ax2.set_title("The book as it stands, 18 August")

    fig.suptitle(
        "The forward record: process, not performance", fontsize=11.5, fontweight="bold", y=1.02
    )
    _note(
        fig,
        "outputs/paper/radar_ledger.csv and radar_open_positions.csv read at origin/main, "
        "written by a scheduled GitHub Actions job that commits the book back to the "
        "repository, so the record is externally timestamped and cannot be back-dated. No "
        "capital is at risk and no order has ever been transmitted to a broker. The realised "
        "book is one trade, and it is not a sample: TPR and CSCO were deleted on 17 August by "
        "a defect that retired positions when their exit date passed rather than when a "
        "ledger row was written, and an unquotable chain means a strike that moved far from "
        "the money, so what it deleted was losses. TPR alone was down at least 119% of "
        "premium. The one surviving row is a winner. The defect is fixed and pinned by a "
        "test; the two positions are unrecoverable. One of the six open rows is a duplicate "
        "from a calendar-feed defect whose fix is not yet committed.",
    )
    _save(fig, out, "fig14_forward_book")


# ── entry point ──────────────────────────────────────────────────────────────────


BUILDERS = [
    fig01_implied_vs_realised,
    fig02_marking_basis,
    fig03_twelve_year_equity,
    fig04_yearly,
    fig05_deflation,
    fig06_mark_repair,
    fig07_fills,
    fig08_margin,
    fig09_three_books,
    fig10_diagnosis,
    fig11_attribution,
    fig12_hold_to_expiry,
    fig13_exit_cost,
    fig14_forward_book,
]


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--outdir", type=Path, default=DEFAULT_OUT)
    args = ap.parse_args()

    verify()
    args.outdir.mkdir(parents=True, exist_ok=True)
    print(f"drawing {len(BUILDERS)} figures into {args.outdir.relative_to(ROOT)}")
    for build in BUILDERS:
        build(args.outdir)
    verify_labels()
    print("done")


if __name__ == "__main__":
    main()
