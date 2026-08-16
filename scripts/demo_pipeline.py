"""
demo_pipeline.py
Run the whole valuation and scoring path end to end on synthetic events.

Why this exists
---------------
The research caches and result artefacts are git-ignored, so a fresh clone can run the
test suite and nothing else. That leaves a new member able to prove the environment
works but unable to see the pipeline work, which is a poor first day.

This builds a synthetic event panel in memory, prices it through the same
``pnl.build_ledger`` the live strategy and the control book both use, applies the same
cost model, and reports through ``screen.score_signal``, the same contract every real
result goes through. Nothing is mocked and no module is bypassed: the only thing that is
not real is the input data.

**The numbers this prints are not a result.** The generator prices announcement risk
fairly by construction, so there is no edge in it to find. What the run demonstrates is
that the arithmetic is sound (the gross book sits near zero, as it must) and what the
measured cost stack does to a book with no gross edge. Every line of output is labelled.

What to read afterwards
-----------------------
``earnings_iv_crush/engine/pnl.py`` for the reference valuation, ``engine/screen.py`` for
the reporting contract, and ``documentation/STRATEGY.md`` for the rules the real book
follows.

Usage
-----
From the project root::

    python scripts/demo_pipeline.py
    python scripts/demo_pipeline.py --events 500 --seed 7 --gate-pctl 0.80
"""

from __future__ import annotations

import argparse

import numpy as np
import pandas as pd

from earnings_iv_crush.engine.costs import CostModel
from earnings_iv_crush.engine.pnl import build_ledger
from earnings_iv_crush.engine.screen import score_signal
from earnings_iv_crush.strategy.filters import expanding_gate_rank

BANNER = "SYNTHETIC DATA - WIRING CHECK ONLY, NOT A RESULT"


# ── synthetic panel ──────────────────────────────────────────────────────────


def make_events(n: int, seed: int) -> pd.DataFrame:
    """Build a synthetic event panel with the columns ``build_ledger`` requires.

    The generator is deliberately fair: the realised move is drawn at exactly the scale
    the entry straddle charges for it, so the synthetic market prices announcement risk
    correctly and there is no edge to find by construction. What the demo then shows is
    the cost stack eating into a book with zero gross edge, which is the right shape to
    have in mind before reading any real result.
    """
    rng = np.random.default_rng(seed)

    dates = pd.to_datetime(
        np.sort(rng.choice(pd.bdate_range("2019-01-02", "2024-12-31"), n, replace=True))
    )
    spot = np.exp(rng.normal(np.log(120.0), 0.55, n))

    # Base volatility, plus the announcement premium the trade is selling.
    base_iv = np.clip(rng.normal(0.34, 0.09, n), 0.12, 0.95)
    premium = np.clip(rng.normal(0.20, 0.09, n), 0.0, 0.70)
    iv_entry = base_iv + premium

    # The crush: most of the premium disappears once the number is public.
    crush = np.clip(rng.normal(0.82, 0.12, n), 0.0, 1.0)
    iv_exit = np.clip(iv_entry - premium * crush, 0.05, None)

    # Fair pricing by construction. The announcement is a jump inside the option's life,
    # so the move it prices is the *excess* variance the premium buys, not the whole
    # 7-day variance: implied_move = sqrt((iv_entry^2 - base_iv^2) * t). Drawing the
    # realised move at exactly that scale means the market charges the right price and
    # there is no gross edge, so whatever the book shows is the cost stack.
    t_entry = 7.0 / 365.0
    implied_move = np.sqrt(np.maximum(iv_entry**2 - base_iv**2, 0.0) * t_entry)
    realised = rng.normal(0.0, implied_move, n)
    spot_exit = spot * (1.0 + realised)

    strike = np.round(spot)  # nearest whole strike, as the real book does

    return pd.DataFrame(
        {
            "ticker": [f"SYN{i % 60:02d}" for i in range(n)],
            "announce_date": dates,
            "entry_date": dates,
            "exit_date": dates + pd.Timedelta(days=1),
            "spot_entry": spot,
            "spot_exit": spot_exit,
            "strike": strike,
            "t_entry": t_entry,
            "t_exit": 6.0 / 365.0,
            "iv_entry": iv_entry,
            "iv_exit": iv_exit,
            # The gated statistic: front minus back ATM implied volatility.
            "iv_term_spread": premium + rng.normal(0.0, 0.02, n),
        }
    )


# ── reporting ────────────────────────────────────────────────────────────────


def report(result, title: str) -> None:
    print(f"\n  {title}")
    print(f"    events            {result.n:>10,}   over {result.n_clusters:,} distinct dates")
    print(f"    hit rate          {result.hit_rate:>10.1%}")
    print(
        f"    mean return       {result.mean:>10.4%}   on margin, {'gross' if result.gross else 'net'}"
    )
    print(f"    Sharpe            {result.sharpe:>10.4f}   basis: {result.sharpe_basis}")
    print(f"    95% interval      [{result.ci_low:+.4f}, {result.ci_high:+.4f}]   date-clustered")
    verdict = "contains zero" if result.ci_low <= 0.0 <= result.ci_high else "excludes zero"
    print(f"                                   {verdict}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[2])
    ap.add_argument("--events", type=int, default=800, help="synthetic events to generate")
    ap.add_argument("--seed", type=int, default=0, help="RNG seed")
    ap.add_argument("--gate-pctl", type=float, default=0.80, help="expanding term-gate percentile")
    args = ap.parse_args()

    print("=" * 78)
    print(f"  {BANNER}")
    print("=" * 78)

    events = make_events(args.events, args.seed)
    print(
        f"\n  Generated {len(events):,} synthetic events across {events['ticker'].nunique()} names,"
    )
    print(
        f"  {events['announce_date'].min():%Y-%m-%d} to {events['announce_date'].max():%Y-%m-%d}."
    )

    # Price every event twice through the reference valuation: once charging commission
    # only, once charging the full measured cost stack. The gap between them is the
    # single most important quantity in this project.
    gross_ledger = build_ledger(events)
    net_ledger = build_ledger(events, costs=CostModel())
    print(
        f"  Priced {len(net_ledger):,} of them into a ledger ({len(net_ledger.columns)} columns)."
    )

    merged = events.merge(
        net_ledger[["ticker", "entry_date", "return_on_margin"]],
        on=["ticker", "entry_date"],
        how="inner",
    )

    gross_result = score_signal(
        gross_ledger["return_on_margin"],
        gross_ledger["entry_date"],
        label="demo-unconditional-gross",
        cadence="event",
        gross=True,
        notes={"data": "synthetic"},
    )
    report(gross_result, "Unconditional book, gross of trading costs")
    print("      The generator prices announcement risk fairly, so this should sit near")
    print("      zero. If it does, the pipeline is arithmetically sound.")

    unconditional = score_signal(
        merged["return_on_margin"],
        merged["announce_date"],
        label="demo-unconditional-net",
        cadence="event",
        gross=False,
        notes={"data": "synthetic"},
    )
    report(unconditional, "Unconditional book, net of trading costs")
    drag = unconditional.mean - gross_result.mean
    print(f"      Cost drag: {drag:+.4%} of margin per trade. On a book with no gross edge")
    print("      that is the whole result, which is the constraint this project exists to attack.")

    # The frozen selector, run through the package's own gate.
    rank = expanding_gate_rank(
        merged["iv_term_spread"].to_numpy(float), merged["announce_date"].to_numpy()
    )
    keep = np.nan_to_num(rank, nan=-9.0) >= args.gate_pctl
    if keep.sum() < 30:
        print(f"\n  Gate admitted only {int(keep.sum())} events; too few to score. Raise --events.")
        return

    gated = merged[keep]
    result = score_signal(
        gated["return_on_margin"],
        gated["announce_date"],
        label=f"demo-term-gate-q{args.gate_pctl:g}",
        cadence="event",
        gross=False,
        notes={"data": "synthetic"},
    )
    report(result, f"Term-gated book (expanding percentile >= {args.gate_pctl:g})")

    print(f"\n  Annualisation factor inferred from the data: {result.periods_per_year:.2f}")
    print("  observations per year, so an annualised Sharpe here would multiply by")
    print(
        f"  sqrt({result.periods_per_year:.2f}) = {np.sqrt(result.periods_per_year):.2f}, not sqrt(252)."
    )

    print("\n" + "=" * 78)
    print(f"  {BANNER}")
    print("  The pipeline is wired correctly. For real results see documentation/STRATEGY.md.")
    print("=" * 78)


if __name__ == "__main__":
    main()
