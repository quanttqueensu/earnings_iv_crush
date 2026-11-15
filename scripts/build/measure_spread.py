"""
measure_spread.py
Ground the cost assumption: measure the *real* ATM round-trip spread on the gated
trades from the tape, replacing the asserted ~2% round-trip used in the validation.

The market-marked backtest assumes a megacap round-trip cost of ~2% (a 4% quoted
spread crossed at the half). The breakeven analysis in ``market_validate.py`` shows
that single assumption is what pins the Sharpe-2 claim, so it is worth measuring.
OPRA NBBO quotes begin 2023-03-28, so this can only price the gated events from that
date on (a few dozen trades), but that is enough to put a number on the spread the
megacap weeklies actually quoted into the close.

Two stages, the first free and always run:

1. **Estimate (free).** ``databento.metadata.get_cost`` is summed over the gated
   2023+ events for the ``cmbp-1`` (full consolidated NBBO) schema on the ATM call and
   put. Nothing is pulled; the script prints the figure and stops unless the spend
   clears a hard cap and ``--pull`` is passed.
2. **Pull (metered, opt-in).** With ``--pull`` and an estimate under ``CAP_USD``, it
   fetches the NBBO ticks for each ATM leg into the disk cache, takes the closing
   quote, and reports the median / IQR of the measured ``(ask - bid) / mid`` - the
   quantity that maps straight onto ``CostModel.bid_ask_pct``. It then re-scores the
   full term+move gated arm at that measured spread under half-spread (realistic) and
   full-spread (punitive) crossing, against the prior 2% assumption, so the headline
   Sharpe rests on the tape rather than a guess.

Run the estimate:  ``python scripts/build/measure_spread.py``
Run the pull:      ``python scripts/build/measure_spread.py --pull``
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from earnings_iv_crush.data import databento_options as dbo  # noqa: E402
from earnings_iv_crush.engine.alpha_adjudication import (  # noqa: E402
    package_relative_spread,
)
from earnings_iv_crush.engine.backtester import backtest  # noqa: E402
from earnings_iv_crush.engine.costs import CostModel  # noqa: E402
from earnings_iv_crush.engine.pnl import ACCOUNT_SIZE  # noqa: E402
from earnings_iv_crush.research.market_marks import (  # noqa: E402
    EVENTS_FULL,
    _gate_masks,
    _ledger,
    _nearest,
    _prepare,
)

OUT_DIR = Path("outputs/research")  # where the measured-cost CSVs (paper sources) land
NBBO_START = pd.Timestamp("2023-03-28")  # OPRA consolidated BBO coverage begins here
SCHEMA = "cmbp-1"  # full consolidated NBBO tick (OPRA): the most accurate closing spread
CAP_USD = 5.0  # hard ceiling: never pull if the estimate exceeds this
NBBO_CACHE = "{date}_nbbo.parquet"


def _osi(root: str, expiry, right: str, strike: float) -> str:
    """OPRA 21-char OSI symbol: 6-char root (space-padded), YYMMDD, C/P, strike*1000.

    Databento OPRA ``raw_symbol`` is the OSI string, so this lets us request the two
    ATM legs by exact symbol - no second ``definition`` pull. ``strike`` must be the
    raw (unadjusted) level the chain carries, which ``strike_mkt`` already is.
    """
    cp = "C" if str(right).upper().startswith("C") else "P"
    return f"{root.ljust(6)}{pd.Timestamp(expiry).strftime('%y%m%d')}{cp}{int(round(strike * 1000)):08d}"


def _front_expiry_strike(e: pd.Series) -> tuple[pd.Timestamp, float] | None:
    """The executed front expiry and ATM strike for an event, from its entry chain
    cache - the same selection ``market_marks`` makes, recovered here so we can name
    the exact OSI legs. Returns ``None`` when the cached chain is missing/empty."""
    path = dbo._cache_path(e["ticker"], pd.Timestamp(e["entry_date"]))
    if not path.exists():
        return None
    ce = pd.read_parquet(path)
    if ce.empty:
        return None
    target_exp = pd.Timestamp(e["entry_date"]) + pd.Timedelta(days=round(e["t_entry"] * 365))
    fexp = ce["expiry"].iloc[(ce["expiry"] - target_exp).abs().argmin()]
    k = _nearest(ce, fexp, e["spot_entry"])
    if not np.isfinite(k):
        return None
    return pd.Timestamp(fexp), float(k)


def _gated_2023(ev: pd.DataFrame, fair: pd.Series) -> pd.DataFrame:
    """The term+move gated events from NBBO coverage on (the priceable slice)."""
    mask = _gate_masks(ev, fair)["term+move"]
    g = ev[mask].copy()
    g = g[pd.to_datetime(g["entry_date"]) >= NBBO_START].reset_index(drop=True)
    return g


def _legs_for(e: pd.Series) -> list[str] | None:
    """The ATM call/put OSI symbols for one gated event, or None if unresolvable."""
    sel = _front_expiry_strike(e)
    if sel is None:
        return None
    fexp, k = sel
    root = dbo._opra_root(e["ticker"])
    return [_osi(root, fexp, "C", k), _osi(root, fexp, "P", k)]


def _window(e: pd.Series) -> tuple[str, str]:
    """Date range covering the entry and exit sessions (end is exclusive +1 day)."""
    start = pd.Timestamp(e["entry_date"]).strftime("%Y-%m-%d")
    end = (pd.Timestamp(e["exit_date"]) + pd.Timedelta(days=1)).strftime("%Y-%m-%d")
    return start, end


def estimate(g: pd.DataFrame) -> float:
    """Sum the free ``get_cost`` over the gated events' ATM legs; print per-event."""
    print(f"--- cost estimate: {SCHEMA} NBBO on {len(g)} gated 2023+ events ---")
    print(f"{'ticker':8s} {'entry':12s} {'legs':>5s} {'est $':>8s}")
    total = 0.0
    for _, e in g.iterrows():
        legs = _legs_for(e)
        if legs is None:
            print(f"{e['ticker']:8s} {str(e['entry_date']):12s} {'-':>5s} {'skip':>8s}")
            continue
        start, end = _window(e)
        try:
            c = dbo.get_cost(legs, start, end, schema=SCHEMA)
        except Exception as exc:  # an unlisted symbol or transient: count as zero, note it
            print(
                f"{e['ticker']:8s} {str(e['entry_date']):12s} {len(legs):5d} {'err':>8s}  ({exc})"
            )
            continue
        total += c
        print(f"{e['ticker']:8s} {str(e['entry_date']):12s} {len(legs):5d} {c:8.4f}")
    print(f"\nestimated total: ${total:.4f}   (cap ${CAP_USD:.2f})")
    return total


def _closing_quote(df: pd.DataFrame, symbol: str, day: pd.Timestamp) -> tuple[float, float]:
    """Dollar width ``ask - bid`` and mid of the last NBBO bar on ``day``.

    Returns the two quantities separately rather than their ratio because the
    straddle's cost is a property of the *package*, not of either leg: the legs
    must be aggregated in dollars before any division. See :func:`_package_spread`.
    """
    sub = df[(df["symbol"] == symbol)]
    if sub.empty:
        return np.nan, np.nan
    ts = pd.to_datetime(sub["ts_event"]).dt.tz_localize(None)
    sub = sub[ts.dt.normalize() == day.normalize()]
    if sub.empty:
        return np.nan, np.nan
    last = sub.iloc[-1]
    bid, ask = float(last["bid_px_00"]), float(last["ask_px_00"])
    mid = 0.5 * (bid + ask)
    if not (mid > 0):
        return np.nan, np.nan
    return ask - bid, mid


def _package_spread(quotes: list[tuple[float, float]]) -> float:
    """Straddle-level relative spread: total dollar width over total mid.

    The strategy trades the two legs as one package, so the cost of unwinding it is
    ``sum(ask_i - bid_i) / sum(mid_i)``. Averaging the legs' *relative* spreads with
    equal weight instead - the estimator this replaces - is unbiased only when the
    legs are worth about the same. That holds at entry and fails at exit: after an
    earnings gap one leg is intrinsic-heavy and the other is a near-worthless tail,
    so an equal weighting loads most of the average onto the leg being closed for
    pennies and overstates the width of the package.

    Confirmed on live IBKR quotes (``scripts/live_quote_snapshot.py``): the two
    estimators agree to 1.00x at the money and diverge monotonically as the strike
    displaces from spot, reaching 1.5x by an 8% displacement.
    """
    if not quotes:
        return np.nan
    widths, mids = zip(*quotes, strict=True)
    return package_relative_spread(widths, mids)


def pull(g: pd.DataFrame, ev: pd.DataFrame, fair: pd.Series) -> None:
    """Fetch the NBBO legs (cached), measure the quoted spread, and re-score the full
    gated arm at the measured spread - so the Sharpe rests on data, not the 2% guess.
    Writes ``measured_spread.csv`` and ``cost_grounded_sharpe.csv`` for the paper."""
    rows = []
    for _, e in g.iterrows():
        legs = _legs_for(e)
        if legs is None:
            continue
        start, end = _window(e)
        cache = dbo._CACHE_ROOT / e["ticker"] / NBBO_CACHE.format(date=start)
        if cache.exists():
            df = pd.read_parquet(cache)
        else:
            df = dbo._get_df(SCHEMA, legs, start, end, "raw_symbol")
            cache.parent.mkdir(parents=True, exist_ok=True)
            df.to_parquet(cache, index=False)
        if df.empty:
            continue
        df = df.reset_index()
        # Full quoted relative spread of the straddle *package* - total dollar width
        # over total mid across the two ATM legs - at entry and exit. This maps
        # directly onto CostModel.bid_ask_pct.
        for day_type, day in (("entry", e["entry_date"]), ("exit", e["exit_date"])):
            quotes = [_closing_quote(df, s, pd.Timestamp(day)) for s in legs]
            spread = _package_spread(quotes)
            if np.isfinite(spread):
                rows.append(
                    {
                        "ticker": e["ticker"],
                        "entry_date": e["entry_date"],
                        "day": day_type,
                        "spread": float(spread),
                    }
                )
    spread_df = pd.DataFrame(rows)
    s = spread_df["spread"].to_numpy() if not spread_df.empty else np.array([], float)
    if not len(s):
        print("no NBBO bars resolved - nothing to report.")
        return

    p = float(np.median(s))  # measured bid_ask_pct (full quoted spread / mid)
    print(f"\n--- measured ATM quoted spread, {len(s)} leg-day observations (closing NBBO) ---")
    print(
        f"bid_ask_pct (full spread/mid): median {p:.2%}  "
        f"IQR [{np.percentile(s, 25):.2%}, {np.percentile(s, 75):.2%}]"
    )
    print(
        "caveat: this is the *closing* NBBO, the widest quote of the session "
        "(liquidity migrates to the auction), so it bounds the tradeable spread from above.\n"
    )

    # Re-score the full term+move gated arm at the measured spread, under two
    # execution styles: cross_fraction=0.5 (market order, half-spread per crossing -
    # the realistic case) and 1.0 (pay the full quoted width both ways - punitive).
    mask = _gate_masks(ev, fair)["term+move"]
    grounded = []
    print(f"{'execution':28s} {'bid_ask_pct':>11s} {'annSh':>7s}")
    cases = [
        ("measured, half-spread cross", p, 0.5),
        ("measured, full-spread cross", p, 1.0),
        ("prior assumption (2% RT)", 0.04, 0.5),
    ]
    for label, bap, cross in cases:
        led = _ledger(
            ev[mask], defined_risk=False, costs=CostModel(bid_ask_pct=bap, cross_fraction=cross)
        )
        sh = backtest(led, ACCOUNT_SIZE)["sharpe"] if len(led) > 1 else np.nan
        print(f"{label:28s} {bap:11.2%} {sh:+7.2f}")
        grounded.append(
            {"execution": label, "bid_ask_pct": bap, "cross_fraction": cross, "ann_sharpe": sh}
        )

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    spread_df.to_csv(OUT_DIR / "measured_spread.csv", index=False)
    pd.DataFrame(grounded).to_csv(OUT_DIR / "cost_grounded_sharpe.csv", index=False)
    print(f"\nwrote measured_spread.csv and cost_grounded_sharpe.csv to {OUT_DIR}/")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--pull", action="store_true", help="pull NBBO if the estimate clears the cap")
    args = ap.parse_args()

    ev, fair = _prepare(EVENTS_FULL)
    g = _gated_2023(ev, fair)
    total = estimate(g)

    if not args.pull:
        print("\nestimate only. Re-run with --pull to fetch (it will stop if over the cap).")
        return
    if total > CAP_USD:
        print(f"\nestimate ${total:.4f} exceeds cap ${CAP_USD:.2f} - not pulling.")
        return
    print(f"\nestimate ${total:.4f} within cap - pulling NBBO...")
    pull(g, ev, fair)


if __name__ == "__main__":
    main()
