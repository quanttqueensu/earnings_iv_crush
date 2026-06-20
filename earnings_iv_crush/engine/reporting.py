"""reporting.py
Research tearsheet for the filtered strategy versus the Agent 0 control.

Turns the scored ledgers into a one-page visual: equity curves, the per-trade
P&L distribution, the vega/gamma/theta/delta P&L attribution that shows where
the money comes from, and the structure mix from the regime selector. A metrics
table (with the bootstrap CI and Deflated Sharpe from ``backtester.compare``) is
written alongside. Outputs land under a git-ignored directory, so nothing here
is committed.

This module implements:

* ``aggregate_pnl_attribution`` — sum the Greek P&L attribution over a ledger.
* ``cumulative_equity``         — equity curve from a ledger.
* ``build_tearsheet``           — render and save the four-panel tearsheet + CSV.
"""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")  # headless: render to file, never to a display
import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402

from .attribution import attribute_straddle_pnl  # noqa: E402
from .backtester import daily_return_series  # noqa: E402

ATTRIBUTION_KEYS = ["vega_pnl", "gamma_pnl", "theta_pnl", "delta_pnl", "residual"]


# ─────────────────────────────────────────────────────────────────────────────
# Aggregations
# ─────────────────────────────────────────────────────────────────────────────


def aggregate_pnl_attribution(ledger: pd.DataFrame, r: float = 0.0) -> dict:
    """
    Sum the Greek P&L attribution across every trade in a ledger.

    Parameters
    ----------
    ledger : pd.DataFrame
        Trade ledger with the entry/exit state columns produced by
        ``pnl.build_ledger``.
    r : float
        Risk-free rate used in the attribution. Defaults to ``0.0``.

    Returns
    -------
    dict
        Summed ``vega_pnl``, ``gamma_pnl``, ``theta_pnl``, ``delta_pnl`` and
        ``residual`` (USD). Zeroed for an empty ledger.
    """
    totals = {k: 0.0 for k in ATTRIBUTION_KEYS}
    if ledger is None or len(ledger) == 0:
        return totals
    for _, row in ledger.iterrows():
        a = attribute_straddle_pnl(
            spot_entry=float(row["spot_entry"]),
            strike=float(row["strike"]),
            t_entry=float(row["t_entry"]),
            t_exit=float(row["t_exit"]),
            iv_entry=float(row["iv_entry"]),
            iv_exit=float(row["iv_exit"]),
            spot_exit=float(row["spot_exit"]),
            r=r,
            contracts=int(row["contracts"]),
        )
        for k in ATTRIBUTION_KEYS:
            totals[k] += a[k]
    return totals


def cumulative_equity(ledger: pd.DataFrame, account: float) -> pd.Series:
    """Equity curve (USD) starting at ``account``, from the ledger's daily P&L."""
    daily = daily_return_series(ledger, account) * account
    if daily.empty:
        return pd.Series([account], dtype=float)
    return account + daily.cumsum()


# ─────────────────────────────────────────────────────────────────────────────
# Tearsheet
# ─────────────────────────────────────────────────────────────────────────────


def build_tearsheet(
    strategy_ledger: pd.DataFrame,
    agent0_ledger: pd.DataFrame,
    comparison: dict,
    account: float,
    outdir: str | Path,
    structure_counts: dict | None = None,
    r: float = 0.0,
) -> Path:
    """
    Render the four-panel research tearsheet and write it with a metrics CSV.

    Panels: (1) strategy vs Agent 0 equity curves, (2) strategy per-trade P&L
    histogram, (3) Greek P&L attribution bar, (4) trade-structure mix (or a
    note when unavailable).

    Parameters
    ----------
    strategy_ledger, agent0_ledger : pd.DataFrame
        Scored ledgers for the filtered strategy and the control.
    comparison : dict
        Output of ``backtester.compare`` (Sharpe spread, CI, DSR, ...).
    account : float
        Starting capital (USD), for the equity curves.
    outdir : str or Path
        Directory to write ``tearsheet.png`` and ``metrics.csv`` into; created
        if absent.
    structure_counts : dict, optional
        Mapping of structure label to count for the mix panel.
    r : float
        Risk-free rate for the attribution. Defaults to ``0.0``.

    Returns
    -------
    Path
        Path to the written ``tearsheet.png``.
    """
    outdir = Path(outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    fig, axes = plt.subplots(2, 2, figsize=(13, 9))
    fig.suptitle("Earnings IV-Crush — Filtered Strategy vs Agent 0", fontsize=14)

    # (1) Equity curves
    ax = axes[0, 0]
    s_eq = cumulative_equity(strategy_ledger, account)
    a_eq = cumulative_equity(agent0_ledger, account)
    ax.plot(range(len(s_eq)), s_eq.to_numpy(), label="Filtered strategy")
    ax.plot(range(len(a_eq)), a_eq.to_numpy(), label="Agent 0 (control)", alpha=0.8)
    ax.set_title("Equity curve (net of costs)")
    ax.set_xlabel("Trading day")
    ax.set_ylabel("Equity (USD)")
    ax.legend(loc="best")

    # (2) Per-trade P&L distribution
    ax = axes[0, 1]
    if strategy_ledger is not None and len(strategy_ledger):
        ax.hist(strategy_ledger["pnl"].to_numpy(), bins=30, color="steelblue")
        ax.axvline(0.0, color="black", linewidth=1)
    ax.set_title("Strategy per-trade P&L")
    ax.set_xlabel("P&L (USD)")
    ax.set_ylabel("Trades")

    # (3) P&L attribution
    ax = axes[1, 0]
    attrib = aggregate_pnl_attribution(strategy_ledger, r=r)
    labels = [k.replace("_pnl", "").title() for k in ATTRIBUTION_KEYS]
    values = [attrib[k] for k in ATTRIBUTION_KEYS]
    colors = ["green" if v >= 0 else "firebrick" for v in values]
    ax.bar(labels, values, color=colors)
    ax.axhline(0.0, color="black", linewidth=1)
    ax.set_title("P&L attribution (the edge is vega)")
    ax.set_ylabel("P&L (USD)")

    # (4) Structure mix
    ax = axes[1, 1]
    if structure_counts:
        ax.bar(list(structure_counts.keys()), list(structure_counts.values()), color="slateblue")
        ax.set_title("Trade-structure mix (regime selector)")
        ax.set_ylabel("Events")
    else:
        ax.axis("off")
        ax.text(0.5, 0.5, "structure mix unavailable", ha="center", va="center")

    fig.tight_layout(rect=(0, 0, 1, 0.96))
    png_path = outdir / "tearsheet.png"
    fig.savefig(png_path, dpi=120)
    plt.close(fig)

    # Metrics CSV
    metrics = {**comparison, **{f"attrib_{k}": v for k, v in attrib.items()}}
    pd.DataFrame([metrics]).to_csv(outdir / "metrics.csv", index=False)

    return png_path
