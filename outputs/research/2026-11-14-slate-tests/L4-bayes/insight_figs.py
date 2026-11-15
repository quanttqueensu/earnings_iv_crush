"""
insight_figs.py
Lane L4: figures and the numbers behind ``insight.md``, from files written once by
``score_heldout.py``: coefficient paths with 95% credible bands, the book gauge, and PIT
histograms. Every number ``insight.md`` quotes is written to ``insight_numbers.json`` here.

Usage
-----
    python outputs/research/2026-11-14-slate-tests/L4-bayes/insight_figs.py
"""

from __future__ import annotations

import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from scipy.stats import t as student_t  # noqa: E402

HERE = Path(__file__).resolve().parent
SERIES = "#2a78d6"  # categorical slot 1 of the reference palette
SECOND = "#eb6834"  # slot 2
INK, MUTED, GRID = "#0b0b0b", "#52514e", "#e4e3df"
CUTS = (pd.Timestamp("2019-01-01"), pd.Timestamp("2025-01-01"))
SNAPS = {"end_2018": "2018-12-31", "end_2024": "2024-12-31", "end_run": "2100-01-01"}


def _style(ax: plt.Axes, cuts: bool = True) -> None:
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    for s in ("left", "bottom"):
        ax.spines[s].set_color(MUTED)
    ax.tick_params(colors=MUTED, labelsize=7)
    ax.grid(axis="y", color=GRID, linewidth=0.6)
    for c in CUTS if cuts else ():
        ax.axvline(c, color=MUTED, linewidth=0.6, linestyle=":")


def coef_paths(path: pd.DataFrame, out: Path) -> dict[str, dict[str, list[float]]]:
    names = [c[2:] for c in path.columns if c.startswith("m_")]
    path = path.assign(date=pd.to_datetime(path["date"]))
    q = student_t.ppf(0.975, path["df"].to_numpy())
    ncol = 4
    nrow = int(np.ceil(len(names) / ncol))
    fig, axes = plt.subplots(nrow, ncol, figsize=(11, 2.2 * nrow), sharex=True, squeeze=False)
    snaps: dict[str, dict[str, list[float]]] = {}
    for ax, nm in zip(axes.ravel(), names, strict=False):
        m, s = path[f"m_{nm}"].to_numpy(), path[f"s_{nm}"].to_numpy()
        ax.fill_between(path["date"], m - q * s, m + q * s, color=SERIES, alpha=0.18, lw=0)
        ax.plot(path["date"], m, color=SERIES, lw=1.5)
        ax.axhline(0, color=INK, lw=0.6)
        ax.set_title(nm, fontsize=8, color=INK, loc="left")
        _style(ax)
        snaps[nm] = {}
        for key, day in SNAPS.items():
            i = int(np.searchsorted(path["date"].to_numpy(), np.datetime64(day), "right")) - 1
            snaps[nm][key] = [float(m[i]), float(m[i] - q[i] * s[i]), float(m[i] + q[i] * s[i])]
    for ax in axes.ravel()[len(names) :]:
        ax.set_visible(False)
    fig.suptitle(
        "Posterior mean and 95% credible band of each coefficient after each update date "
        "(model scale; dotted lines: 2019 and 2025)",
        fontsize=9,
        color=INK,
    )
    fig.tight_layout()
    fig.savefig(out, dpi=150)
    plt.close(fig)
    return snaps


def gauge(gb: pd.DataFrame, bm: pd.DataFrame, out: Path) -> None:
    gb = gb.assign(date=pd.to_datetime(gb["date"]))
    bm = bm.assign(date=pd.to_datetime(bm["date"]))
    fig, (a1, a2) = plt.subplots(2, 1, figsize=(9, 5.2), sharex=True)
    a1.plot(gb["date"], gb["p_mean_pos_deff"], color=SERIES, lw=1.5, label="with design effect")
    a1.plot(gb["date"], gb["p_mean_pos"], color=SECOND, lw=1.0, label="raw")
    a1.axhline(0.5, color=INK, lw=0.6)
    a1.set_ylabel("P(intercept < 0)", fontsize=8, color=MUTED)
    a1.set_ylim(-0.02, 1.02)
    a1.legend(fontsize=7, frameon=False, loc="upper left")
    a1.set_title(
        "Baseline intercept gauge: P(the median trade gains), loss-ratio scale",
        fontsize=8,
        color=INK,
        loc="left",
    )
    a2.fill_between(bm["date"], bm["low"], bm["high"], color=SERIES, alpha=0.18, lw=0)
    a2.plot(bm["date"], bm["mean"], color=SERIES, lw=1.5)
    a2.axhline(0, color=INK, lw=0.6)
    a2.set_ylabel("% of m0 per trade", fontsize=8, color=MUTED)
    a2.set_title(
        "Event-weighted mean H_corr of settled trades, date-clustered 95%", fontsize=8,
        color=INK, loc="left",
    )  # fmt: skip
    for ax in (a1, a2):
        _style(ax)
    fig.tight_layout()
    fig.savefig(out, dpi=150)
    plt.close(fig)


def pit(run: pd.DataFrame, out: Path) -> None:
    fig, axes = plt.subplots(1, 3, figsize=(10, 2.6), sharey=True)
    for ax, blk in zip(axes, ("2013-18", "2019-24", "2025-26"), strict=True):
        r = run[(run["block"] == blk) & run["m_scored"] & run["m_pit"].notna()]
        bins = np.linspace(0, 1, 11)
        cm, _ = np.histogram(r["m_pit"], bins)
        cb, _ = np.histogram(r["b_pit"], bins)
        x = bins[:-1] + 0.05
        ax.bar(x - 0.021, cm / len(r), width=0.04, color=SERIES, label="model")
        ax.bar(x + 0.021, cb / len(r), width=0.04, color=SECOND, label="baseline")
        ax.axhline(0.1, color=INK, lw=0.6)
        ax.set_title(f"PIT, {blk} (N {len(r)})", fontsize=8, color=INK, loc="left")
        _style(ax, cuts=False)
    axes[0].legend(fontsize=7, frameon=False)
    fig.tight_layout()
    fig.savefig(out, dpi=150)
    plt.close(fig)


def main() -> None:
    path = pd.read_csv(HERE / "coef_path_H_corr.csv", parse_dates=["date"])
    gm = pd.read_csv(HERE / "gauge_model_H_corr.csv", parse_dates=["date"])
    # Plot from the first update date with 200 settled trades, when predictions start to count.
    first = gm.loc[gm["n_settled"] >= 200, "date"].min()
    snaps = coef_paths(
        path[path["date"] >= first].reset_index(drop=True), HERE / "fig_coef_paths.png"
    )
    gauge(
        pd.read_csv(HERE / "gauge_baseline_H_corr.csv"),
        pd.read_csv(HERE / "gauge_book_mean.csv"),
        HERE / "fig_gauge.png",
    )
    run = pd.read_parquet(HERE / "run_H_corr.parquet")
    pit(run, HERE / "fig_pit.png")
    weight = {
        nm: {
            "excludes_zero_end_2018": bool(v["end_2018"][1] > 0 or v["end_2018"][2] < 0),
            "excludes_zero_end_run": bool(v["end_run"][1] > 0 or v["end_run"][2] < 0),
            "sign_stable": bool(np.sign(v["end_2018"][0]) == np.sign(v["end_run"][0])),
        }
        for nm, v in snaps.items()
    }
    (HERE / "insight_numbers.json").write_text(
        json.dumps({"snapshots": snaps, "weight": weight}, indent=2) + "\n", encoding="utf-8"
    )
    print("written fig_coef_paths.png, fig_gauge.png, fig_pit.png, insight_numbers.json")


if __name__ == "__main__":
    main()
