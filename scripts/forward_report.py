"""
forward_report.py
Live significance report for the forward paper book as it accrues.

Reads the forward ledgers written by ``scripts/paper_trade_ibkr.py forward-exit``
(no-stop book, hard-stop book, and the fill/spread reconciliation) and reports,
per book: N, hit rate, mean per-trade return on margin and per-trade Sharpe, each
with a date-clustered bootstrap CI that resamples announcement dates rather than
trades (5,000 draws, seed 0, as in the research scorers), because trades on one
announcement session share a gap and a closing book. An annualised Sharpe appears
only as a labelled secondary figure, and only when its factor can be derived from
the book's own trade cadence; no default factor is ever substituted. The
reconciliation section compares realised round-trip costs to the canonical
break-even so the forward book is scored on the same basis as the backtest.

The report is honest by construction: with zero or few trades it says so and
prints nothing that could be mistaken for evidence. All statistics reuse
``earnings_iv_crush.engine.stats`` so forward and backtest share one basis.

Usage
-----
    python scripts/forward_report.py
    python scripts/forward_report.py --out _private/reports/forward_report.md
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Callable
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from earnings_iv_crush.engine.alpha_adjudication import add_return_measures  # noqa: E402
from earnings_iv_crush.engine.event_study import cluster_bootstrap_ci  # noqa: E402
from earnings_iv_crush.live import paper_book  # noqa: E402
from earnings_iv_crush.live.forward_test import BREAKEVEN_ROUND_TRIP, FORWARD  # noqa: E402

PROJECT = Path(__file__).resolve().parents[1]
MIN_TRADES_FOR_CI = 8  # below this a bootstrap CI is noise dressed as inference
# Resampling three dates cannot describe a sampling distribution, whatever the trade count.
MIN_CLUSTERS_FOR_CI = 5
MIN_SPAN_DAYS = 30  # a shorter span cannot pin down how many trades a year the book makes
N_BOOT = 5000  # matches the research scorers
SEED = 0
MIN_TRADES_FOR_DECISION = 40  # pre-registered paper sample-size gate


# ─────────────────────────────────────────────────────────────────────────────
# Per-book statistics
# ─────────────────────────────────────────────────────────────────────────────


def _cluster_keys(ledger: pd.DataFrame) -> pd.Series:
    """The announcement each trade belongs to, as a date string.

    Trades on the same announcement session share one overnight gap and one closing book,
    so they are one draw, not several. The forward ledger stores no announcement date; the
    exit session is the announcement-reaction session (entry is the session before), so it
    identifies the same cluster. ``announce_date`` is used when a ledger carries it.
    """
    col = "announce_date" if "announce_date" in ledger.columns else "exit_date"
    return pd.to_datetime(ledger[col]).dt.strftime("%Y-%m-%d")


def _per_trade_sharpe(x: np.ndarray) -> float:
    sd = float(np.std(x, ddof=1)) if len(x) > 1 else float("nan")
    return float(np.mean(x) / sd) if sd > 0 else float("nan")


def clustered_ci(
    values: np.ndarray, keys: np.ndarray, stat: Callable[[np.ndarray], float]
) -> tuple[float, float]:
    """Date-clustered percentile bootstrap: resample announcement dates, not trades.

    Matches the research scorers (5,000 draws, seed 0), so a forward interval and a
    backtest interval are read on one basis.
    """
    return cluster_bootstrap_ci(values, keys, stat, n_boot=N_BOOT, seed=SEED)


def derived_periods_per_year(dates: pd.Series) -> tuple[float, str] | None:
    """Trades per year from the book's own span, with its derivation, or None.

    None when the factor cannot be derived (fewer than two distinct dates or a span shorter
    than ``MIN_SPAN_DAYS``); no default is substituted, because a defaulted 252 on an event
    book inflates the annualised figure several times over.
    """
    d = pd.to_datetime(dates)
    span = (d.max() - d.min()).days
    if d.nunique() < 2 or span < MIN_SPAN_DAYS:
        return None
    ppy = len(d) * 365.25 / span
    return ppy, f"{len(d)} trades over {span / 365.25:.2f} years = {ppy:.1f} trades/yr"


def book_stats(ledger: pd.DataFrame, label: str) -> list[str]:
    """Markdown lines for one book. Every figure is per trade unless labelled otherwise."""
    lines = [f"### {label}", ""]
    n = len(ledger)
    if n == 0:
        return lines + ["No completed trades yet.", ""]

    frame = add_return_measures(
        pd.DataFrame(
            {
                "entry_credit": ledger.get("entry_credit"),
                "exit_value": ledger.get("exit_value"),
                "pnl": ledger.get("pnl"),
                "rom": pd.Series(ledger["return_on_margin"], dtype=float).values,
                "exit_date": pd.to_datetime(ledger["exit_date"]).values,
                "cluster": _cluster_keys(ledger).values,
            }
        )
    ).dropna(subset=["rom", "exit_date"])
    rom = frame["rom"].to_numpy(dtype=float)
    keys = frame["cluster"].to_numpy()
    n_clusters = len(set(keys))
    hit = float((rom > 0).mean())
    per_trade_sr = _per_trade_sharpe(rom)
    sd = float(np.std(rom, ddof=1)) if len(rom) > 1 else float("nan")

    lines.append(f"- Trades: N = {n} across {n_clusters} announcement date(s); hit rate {hit:.1%}")
    lines.append(
        f"- Mean return on margin: {rom.mean():+.4f} per trade, net of commission (sd {sd:.4f})"
    )
    lines.append(f"- Sharpe: {per_trade_sr:+.3f} per trade (mean / sd of per-trade returns)")
    premium = (
        pd.to_numeric(frame["net_return_on_premium"], errors="coerce").dropna()
        if "net_return_on_premium" in frame
        else pd.Series(dtype=float)
    )
    if not premium.empty:
        lines.append(f"- Mean net return on premium: {premium.mean():+.2%} per trade")
    if n < MIN_TRADES_FOR_DECISION:
        lines.append(
            f"- Validation status: observational only; N < {MIN_TRADES_FOR_DECISION} paper trades"
        )
    else:
        lines.append(
            f"- Validation status: minimum paper sample reached (N >= {MIN_TRADES_FOR_DECISION}); "
            "still not a significance claim"
        )

    if n >= MIN_TRADES_FOR_CI and n_clusters >= MIN_CLUSTERS_FOR_CI:
        mlo, mhi = clustered_ci(rom, keys, np.mean)
        slo, shi = clustered_ci(rom, keys, _per_trade_sharpe)
        verdict = "excludes zero" if slo > 0 or shi < 0 else "straddles zero"
        basis = f"date-clustered bootstrap, {N_BOOT:,} draws over {n_clusters} dates, seed {SEED}"
        lines.append(f"- 95% CI, mean return on margin per trade: [{mlo:+.4f}, {mhi:+.4f}]")
        lines.append(f"- 95% CI, Sharpe per trade: [{slo:+.3f}, {shi:+.3f}], {verdict} ({basis})")
    else:
        lines.append(
            f"- CI withheld: needs N >= {MIN_TRADES_FOR_CI} trades on >= {MIN_CLUSTERS_FOR_CI} "
            f"announcement dates (have {n} on {n_clusters})"
        )

    factor = derived_periods_per_year(frame["exit_date"])
    if factor is not None and np.isfinite(per_trade_sr):
        ppy, how = factor
        lines.append(
            f"- Annualised Sharpe (secondary): {per_trade_sr * np.sqrt(ppy):+.2f}, per-trade "
            f"Sharpe x sqrt({ppy:.1f}), factor derived from the book's own cadence ({how})"
        )
    else:
        lines.append(
            "- Annualised Sharpe withheld: the trade cadence cannot yet be derived from the book"
        )
    lines.append("")
    return lines


def reconciliation_stats(recon: pd.DataFrame) -> list[str]:
    """Cost reconciliation against the canonical break-even."""
    lines = ["### Cost reconciliation", ""]
    if len(recon) == 0:
        return lines + ["No exits reconciled yet.", ""]
    rt = pd.Series(recon["realised_round_trip_cost"], dtype=float).dropna()
    over = pd.Series(recon["over_breakeven"]).astype(bool)
    slip = pd.Series(recon["slippage_vs_mid_ps"], dtype=float).dropna()
    lines.append(
        f"- Realised round-trip cost: mean {rt.mean():.2%} of premium "
        f"vs break-even {BREAKEVEN_ROUND_TRIP:.2%}; {over.mean():.0%} of exits over break-even"
    )
    cost_verdict = (
        "passes the cost gate" if rt.mean() <= BREAKEVEN_ROUND_TRIP else "fails the cost gate"
    )
    lines.append(f"- Execution verdict: {cost_verdict}; this is not evidence of alpha by itself")
    lines.append(f"- Managed-exit slippage vs assumed mid: mean {slip.mean():+.4f} $/share")
    if "stop_was_triggered" in recon:
        trig = pd.Series(recon["stop_was_triggered"]).astype(bool)
        if trig.any():
            gap = pd.Series(recon.loc[trig, "stop_gap_slippage_ps"], dtype=float)
            lines.append(
                f"- Stop triggered on {int(trig.sum())} exit(s); "
                f"mean gap slippage {gap.mean():+.4f} $/share vs the no-stop book"
            )
        else:
            lines.append("- Stop never triggered so far; gap slippage unmeasured")
    lines.append("")
    return lines


# ─────────────────────────────────────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────────────────────────────────────


def _load(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    return pd.read_parquet(path)


def harness_health(stale_days: int = 5) -> list[str]:
    """Report whether the entry pass is alive, before reporting what it found.

    An empty book has three causes that read identically in a results table: the
    harness has not run, it ran and found no announcements, or it ran and failed
    on every candidate. The third is what happened for six weeks on a market-data
    entitlement error, while the report printed a clean "book is empty" each day.
    The heartbeat separates them and this section states which one holds, so an
    empty book is never mistaken for a patient one.
    """
    hb = paper_book.load_heartbeat()
    out = ["### Harness health", ""]
    if hb.empty:
        out += [
            "**ALARM: no entry pass has ever recorded a heartbeat.** The book being "
            "empty says nothing about the strategy; the harness is not known to have "
            "run. Check the scheduled task before reading anything below.",
            "",
        ]
        return out

    hb = hb.copy()
    hb["asof"] = pd.to_datetime(hb["asof"])
    last = hb.sort_values("asof").iloc[-1]
    age = (pd.Timestamp.today().normalize() - last["asof"]).days
    recent = hb[hb["asof"] >= hb["asof"].max() - pd.Timedelta(days=30)]
    seen, priced = int(recent["n_candidates"].sum()), int(recent["n_priced"].sum())

    out += [
        f"Last entry pass: {last['asof']:%Y-%m-%d} ({age}d ago). "
        f"Trailing 30d: {seen} candidates seen, {priced} priced, "
        f"{int(recent['n_gated'].sum())} gated, {int(recent['n_entered'].sum())} entered.",
        "",
    ]
    if age > stale_days:
        out += [
            f"**ALARM: the last entry pass was {age} days ago.** The scheduled task is "
            "not firing; an empty book here is a scheduling fault, not evidence.",
            "",
        ]
    if seen > 0 and priced == 0:
        out += [
            "**ALARM: every candidate in the last 30 days failed to price.** This is a "
            "data or connection fault, not a quiet market. Check the IB market-data "
            "entitlement (`LiveConfig.ib_market_data_type`); an unsubscribed paper "
            "account returns NaN on every field and skips every name silently.",
            "",
        ]
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", type=Path, default=None, help="also write the report here")
    args = ap.parse_args()

    nostop = _load(PROJECT / FORWARD.nostop_ledger_path)
    stop = _load(PROJECT / FORWARD.stop_ledger_path)
    recon = _load(PROJECT / FORWARD.reconciliation_path)

    lines = [
        f"# Forward paper-book report, {datetime.now():%Y-%m-%d}",
        "",
        "Locked baseline: term gate q=0.80, move/skew gates off, naked short straddle.",
        "All returns are per-trade return on margin, net of commission; fills per the",
        "managed mid-seeking exit. Backtest prior: per-trade Sharpe ~+0.1, CI through zero.",
        "",
    ]
    lines += harness_health()
    if len(nostop) == 0 and len(stop) == 0:
        lines += [
            "**Book is empty: the forward test has not recorded a completed trade yet.**",
            "No inference is possible; this is a status report, not evidence.",
            "",
        ]
    lines += book_stats(nostop, "No-stop book (managed exit)")
    lines += book_stats(stop, f"Hard-stop book (stop at {FORWARD.stop_loss_rom:+.0%} RoM)")
    lines += reconciliation_stats(recon)

    report = "\n".join(lines)
    print(report)
    if args.out is not None:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(report, encoding="utf-8")
        print(f"\nwritten: {args.out.resolve()}")


if __name__ == "__main__":
    main()
