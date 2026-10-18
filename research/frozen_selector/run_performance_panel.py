"""
run_performance_panel.py
Full performance panel for the quote-marked book: risk, drawdown, and selection-bias deflation.

``run_extension_verdict.py`` answers whether the edge is distinguishable from zero. That is
the inferential question and it is not the same as the risk question, which is what the
equity curve does between the first trade and the last. A per-trade Sharpe says nothing
about how much of the account is at risk at the worst moment, and a book with 30 trades a
year can carry a drawdown that no Sharpe would reveal.

Every ratio here is computed on the per-trade series, not a daily series, because the book
holds one overnight per event and is flat in between. Annualisation therefore uses the
book's own realised cadence, ``sqrt(trades per year)``, at roughly 30-35 per year. The
familiar ``sqrt(252)`` assumes a position every trading day and would inflate these Sharpes
by about a factor of 2.7; it is the single most common way an event book is oversold.

Drawdown is reported in dollars and as a fraction of the ``ACCOUNT_SIZE`` the sizing rule
already assumes, so it is comparable to the P&L rather than to the margin denominator that
``return_on_margin`` uses.

PSR and DSR are evaluated against the trial family recorded in
``outputs/research/dsr_q80_trial_surface.csv``. Deflating against a family invented here
would defeat the purpose: the count has to be the number of configurations actually tried
before this specification was chosen, not a number chosen to make the result survive.

Run: ``python research/frozen_selector/run_performance_panel.py``
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats as sps

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import earnings_iv_crush.research.market_marks as mv  # noqa: E402
from earnings_iv_crush.data import databento_quotes as dq  # noqa: E402
from earnings_iv_crush.engine.stats import (  # noqa: E402
    deflated_sharpe_ratio,
    max_drawdown_duration,
    probabilistic_sharpe_ratio,
    profit_factor,
    win_loss_ratio,
)
from earnings_iv_crush.research.gates import expanding_high_term_mask  # noqa: E402

EXTENSION = "data/processed/events_megacap_quotes_2013_2018.parquet"
TRIALS = Path("outputs/research/dsr_q80_trial_surface.csv")
OUT = Path("outputs/research/performance_panel.csv")
CURVE = Path("outputs/research/equity_curves.csv")
Q = 0.80
ACCOUNT = mv.ACCOUNT_SIZE


# ── trial family ──────────────────────────────────────────────────────────────


def _trial_family() -> tuple[int, float, str]:
    """The recorded trial count and Sharpe dispersion used to deflate.

    The widest recorded family is taken deliberately. A DSR is a claim about how much of
    the observed Sharpe survives the search that produced it, so understating the search
    is the one direction that flatters the result.
    """
    if not TRIALS.exists():
        raise SystemExit(f"missing recorded trial family: {TRIALS}")
    t = pd.read_csv(TRIALS)
    row = t.sort_values(["n_trials", "sr_trials_std"]).iloc[-1]
    return int(row["n_trials"]), float(row["sr_trials_std"]), str(row["dispersion_source"])


# ── panel ─────────────────────────────────────────────────────────────────────


def _drawdown(equity: pd.Series) -> tuple[float, float]:
    """Maximum peak-to-trough decline of the cumulative P&L, in dollars."""
    peak = equity.cummax()
    dd = equity - peak
    return float(dd.min()), float(dd.min() / ACCOUNT)


def _panel(label: str, events_path: str, n_trials: int, sr_std: float) -> tuple[dict, pd.DataFrame]:
    ev, _ = mv._prepare(events_path, chain_path=dq.cache_path)
    mask = np.asarray(expanding_high_term_mask(ev, Q), dtype=bool)
    led = mv._ledger(ev[mask].reset_index(drop=True), defined_risk=False, costs=mv.MEGACAP_COST)
    led = led.dropna(subset=["return_on_margin"]).copy()
    led["entry_date"] = pd.to_datetime(led["entry_date"])
    led = led.sort_values("entry_date").reset_index(drop=True)
    if len(led) < 2:
        return {"block": label, "n": len(led)}, pd.DataFrame()

    rom = pd.to_numeric(led["return_on_margin"], errors="coerce")
    pnl = pd.to_numeric(led["pnl"], errors="coerce")
    n = len(rom)
    s = float(rom.mean() / rom.std(ddof=1))

    span = max((led["entry_date"].max() - led["entry_date"].min()).days / 365.25, 1e-9)
    tpy = n / span
    ann_factor = np.sqrt(tpy)

    # Downside deviation against a zero target: only losing trades contribute, which is the
    # relevant asymmetry for a short-vol book whose losses are the fat side.
    downside = rom[rom < 0]
    dd_dev = float(np.sqrt((downside**2).sum() / n)) if len(downside) else np.nan
    sortino = float(rom.mean() / dd_dev) if dd_dev and np.isfinite(dd_dev) else np.nan

    equity = pnl.cumsum()
    mdd, mdd_pct = _drawdown(equity)
    ann_pnl = float(pnl.sum() / span)
    calmar = float(ann_pnl / abs(mdd)) if mdd else np.nan

    se = float(np.sqrt((1 + s**2 / 2) / n))
    z = s / se
    psr = probabilistic_sharpe_ratio(rom, sr_benchmark_per_period=0.0)
    dsr = deflated_sharpe_ratio(rom, n_trials=n_trials, sr_trials_std=sr_std)

    row = {
        "block": label,
        "n": n,
        "span_years": span,
        "trades_per_year": tpy,
        "hit_rate": float((rom > 0).mean()),
        "mean_rom": float(rom.mean()),
        "median_rom": float(rom.median()),
        "rom_skew": float(sps.skew(rom)),
        "rom_kurtosis": float(sps.kurtosis(rom, fisher=False)),
        "per_trade_sharpe": s,
        "annualised_sharpe": s * ann_factor,
        "ann_factor": ann_factor,
        "per_trade_sortino": sortino,
        "annualised_sortino": sortino * ann_factor if np.isfinite(sortino) else np.nan,
        "total_pnl": float(pnl.sum()),
        "ann_pnl": ann_pnl,
        "ann_return_on_account": ann_pnl / ACCOUNT,
        "max_drawdown_usd": mdd,
        "max_drawdown_pct_account": mdd_pct,
        "calmar": calmar,
        "dd_duration_trades": int(max_drawdown_duration(equity)),
        "profit_factor": float(profit_factor(pnl)),
        "win_loss_ratio": float(win_loss_ratio(pnl)),
        "best_trade_usd": float(pnl.max()),
        "worst_trade_usd": float(pnl.min()),
        "z": z,
        "one_sided_p": float(1 - sps.norm.cdf(z)),
        "psr_vs_zero": float(psr),
        "dsr": float(dsr),
        "n_trials": n_trials,
        "sr_trials_std": sr_std,
    }
    curve = pd.DataFrame(
        {"block": label, "entry_date": led["entry_date"], "pnl": pnl, "equity": equity}
    )
    return row, curve


def _report(r: dict) -> None:
    if r.get("n", 0) < 2:
        print(f"\n  {r['block']}: too few marked trades to score (N={r.get('n')})")
        return
    print(f"\n  {r['block']}")
    print(f"    N / span            {r['n']} trades over {r['span_years']:.2f} yr")
    print(f"    hit rate            {r['hit_rate']:.1%}")
    print(f"    mean / median RoM   {r['mean_rom']:+.4f} / {r['median_rom']:+.4f}")
    print(f"    skew / kurtosis     {r['rom_skew']:+.2f} / {r['rom_kurtosis']:.2f}")
    print(f"    Sharpe  per-trade   {r['per_trade_sharpe']:+.6f}")
    print(
        f"            annualised  {r['annualised_sharpe']:+.3f} "
        f"(x sqrt({r['trades_per_year']:.1f}) = {r['ann_factor']:.3f}, NOT sqrt(252))"
    )
    print(
        f"    Sortino per-trade   {r['per_trade_sortino']:+.4f}  "
        f"annualised {r['annualised_sortino']:+.3f}"
    )
    print(f"    total P&L           ${r['total_pnl']:,.0f}")
    print(
        f"    annualised P&L      ${r['ann_pnl']:,.0f}  "
        f"({r['ann_return_on_account']:+.2%} on ${ACCOUNT:,.0f})"
    )
    print(
        f"    max drawdown        ${r['max_drawdown_usd']:,.0f}  "
        f"({r['max_drawdown_pct_account']:.2%} of account)"
    )
    print(f"    Calmar              {r['calmar']:+.3f}  (ann P&L / |max DD|)")
    print(f"    DD duration         {r['dd_duration_trades']} trades peak-to-recovery")
    print(f"    profit factor       {r['profit_factor']:.3f}")
    print(f"    best / worst trade  ${r['best_trade_usd']:,.0f} / ${r['worst_trade_usd']:,.0f}")
    print(f"    z / one-sided p     {r['z']:+.2f} / {r['one_sided_p']:.4f}")
    print(f"    PSR vs zero         {r['psr_vs_zero']:.4f}")
    print(f"    DSR                 {r['dsr']:.4f}  (deflated against {r['n_trials']} trials)")


def main() -> None:
    n_trials, sr_std, source = _trial_family()
    print("Frozen spec: expanding pooled term gate q=0.80, quote marks, MEGACAP_COST")
    print(f"Deflating against the recorded family: {n_trials} trials, dispersion '{source}'")
    print("Annualisation uses the book's realised cadence, never sqrt(252).")

    rows, curves = [], []
    for label, path in [
        ("2019-2024 (original)", mv.EVENTS_FULL),
        ("2013-2018 (extension)", EXTENSION),
    ]:
        r, c = _panel(label, path, n_trials, sr_std)
        _report(r)
        rows.append(r)
        if not c.empty:
            curves.append(c)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame([r for r in rows if r.get("n", 0) > 1]).to_csv(OUT, index=False)
    if curves:
        pd.concat(curves).to_csv(CURVE, index=False)
    print(f"\nwritten: {OUT.resolve()}")
    print(f"written: {CURVE.resolve()}")


if __name__ == "__main__":
    main()
