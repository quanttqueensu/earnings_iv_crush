"""
run_driver_attribution.py
Is the gated book's P&L carried by theta, by vega, or by the underlying move?

The paper's stated mechanism is an implied-volatility crush, which is a vega claim.
Until now the figure asserting it (``fig01_attribution``) carried four constants that
appear in no artifact in this repository. This script derives the decomposition from the
marked book itself and writes it to disk, so the claim can be checked.

Method
------
Gross P&L per share is ``straddle(entry state) - straddle(exit state)``. Walk from one
to the other changing a single variable at a time; the three differences then sum to the
total with no residual:

    theta = BS(S0,K,t0,v0) - BS(S0,K,t1,v0)     time decay, at the entry spot and vol
    vega  = BS(S0,K,t1,v0) - BS(S0,K,t1,v1)     the vol move, at the decayed tenor
    spot  = BS(S0,K,t1,v1) - BS(S1,K,t1,v1)     the underlying move, last

Sign convention is the short book's: positive means the leg made money.

The vols are **inverted from the book's own straddle marks** rather than taken from the
event table's ``iv_entry``/``iv_exit``. That matters. The event table re-picks the ATM
strike at exit, so its exit IV describes a contract the book does not hold, and a
decomposition built on it describes a different position. Inverting ``credit_mkt`` and
``exit_mkt`` at the strike actually traded makes ``BS(entry) = credit_mkt`` and
``BS(exit) = exit_mkt`` identities, so the three legs reconcile to the realised
market-marked P&L exactly rather than approximately.

A one-at-a-time decomposition is path-dependent, since the cross terms have to be
attributed somewhere. Both orderings are therefore computed and both reported. Where
they agree on which leg dominates, the reading is robust to the ordering; where they do
not, no attribution claim should be made.

Run
---
    python research/frozen_selector/run_driver_attribution.py                # trade-marked book
    python research/frozen_selector/run_driver_attribution.py --book quote   # quote-marked book
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import earnings_iv_crush.research.market_marks as mv  # noqa: E402
from earnings_iv_crush.data import databento_quotes as dq  # noqa: E402
from earnings_iv_crush.engine.greeks import straddle_price  # noqa: E402
from earnings_iv_crush.engine.pnl import ACCOUNT_SIZE, size_contracts  # noqa: E402
from earnings_iv_crush.research.gates import expanding_high_term_mask  # noqa: E402

OUT = Path("outputs/research/driver_attribution.csv")
Q = 0.80
R = 0.0
MULT = 100


def _straddle(s: float, k: float, t: float, v: float) -> float:
    if t <= 0 or v <= 0:
        return abs(s - k)
    return straddle_price(s, k, t, R, v)


def _implied_from_mark(mark: float, s: float, k: float, t: float) -> float:
    """Vol that reprices the straddle mark exactly, by inverting each leg's half.

    A straddle is monotone in vol, so bisecting on the straddle price is well posed.
    ``implied_vol`` inverts a single leg, so the straddle is bracketed directly here.
    """
    if not np.isfinite(mark) or mark <= 0 or t <= 0:
        return float("nan")
    lo, hi = 1e-6, 5.0
    if _straddle(s, k, t, hi) < mark:
        return float("nan")
    if _straddle(s, k, t, lo) > mark:
        return float("nan")
    for _ in range(200):
        mid = 0.5 * (lo + hi)
        if _straddle(s, k, t, mid) < mark:
            lo = mid
        else:
            hi = mid
        if hi - lo < 1e-10:
            break
    return 0.5 * (lo + hi)


def _legs(row: pd.Series, order: str) -> tuple[float, float, float]:
    s0, s1 = float(row["spot_entry"]), float(row["spot_exit"])
    k = float(row["strike_mkt"])
    t0, t1 = float(row["t_entry"]), float(row["t_exit"])
    v0, v1 = float(row["iv_mark_entry"]), float(row["iv_mark_exit"])

    if order == "tvs":
        a, b = _straddle(s0, k, t0, v0), _straddle(s0, k, t1, v0)
        c = _straddle(s0, k, t1, v1)
        d = _straddle(s1, k, t1, v1)
        return a - b, b - c, c - d
    a, b = _straddle(s0, k, t0, v0), _straddle(s1, k, t0, v0)
    c = _straddle(s1, k, t0, v1)
    d = _straddle(s1, k, t1, v1)
    return c - d, b - c, a - b


def _attribute(book: pd.DataFrame, lines: list[str], label: str) -> list[dict]:
    gross = float(((book["credit_mkt"] - book["exit_mkt"]) * MULT * book["contracts"]).sum())
    lines.append(f"\n-- {label} --")
    lines.append(f"  N trades            {len(book)}")
    lines.append(f"  Gross P&L           ${gross / 1000:+.1f}k")
    lines.append(
        f"  Mark-implied crush  {(book['iv_mark_entry'] - book['iv_mark_exit']).mean():+.4f}  "
        f"({(book['iv_mark_entry'] > book['iv_mark_exit']).mean():.1%} fall)"
    )
    rows: list[dict] = []
    for order in ("tvs", "svt"):
        legs = book.apply(lambda r, o=order: _legs(r, o), axis=1, result_type="expand")
        legs.columns = ["theta", "vega", "spot"]
        scale = book["contracts"] * MULT
        a = {name: float((legs[name] * scale).sum()) for name in legs.columns}
        tot = sum(a.values())
        lines.append(
            f"  order {order}:  theta ${a['theta'] / 1000:+8.1f}k   "
            f"vega ${a['vega'] / 1000:+8.1f}k   spot ${a['spot'] / 1000:+8.1f}k   "
            f"(sum {tot / 1000:+.1f}k, residual {(tot - gross) / 1000:+.3f}k)"
        )
        rows.append({"book": label, "order": order, "n": len(book), "gross": gross, **a})
    return rows


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--book", choices=("trade", "quote"), default="trade")
    args = ap.parse_args()

    chain_path = dq.cache_path if args.book == "quote" else None
    ev, _ = mv._prepare(mv.EVENTS_FULL, chain_path=chain_path)
    mask = np.asarray(expanding_high_term_mask(ev, Q), dtype=bool)

    book = ev[mask].copy()
    book = book.dropna(subset=["credit_mkt", "exit_mkt", "strike_mkt"])
    book = book[book["credit_mkt"] > 0].reset_index(drop=True)
    book["contracts"] = [
        size_contracts(
            ACCOUNT_SIZE,
            float(r["spot_entry"]),
            float(r["strike_mkt"]),
            float(r["credit_mkt"]),
            mv.FRACTION,
        )
        for _, r in book.iterrows()
    ]
    book = book[book["contracts"] > 0].reset_index(drop=True)

    book["iv_mark_entry"] = [
        _implied_from_mark(
            float(r["credit_mkt"]),
            float(r["spot_entry"]),
            float(r["strike_mkt"]),
            float(r["t_entry"]),
        )
        for _, r in book.iterrows()
    ]
    book["iv_mark_exit"] = [
        _implied_from_mark(
            float(r["exit_mkt"]), float(r["spot_exit"]), float(r["strike_mkt"]), float(r["t_exit"])
        )
        for _, r in book.iterrows()
    ]
    n_before = len(book)
    book = book.dropna(subset=["iv_mark_entry", "iv_mark_exit"]).reset_index(drop=True)
    if n_before != len(book):
        # A mark that no vol can reproduce is one that breaches the no-arbitrage bounds;
        # counting them here rather than dropping them silently is the point.
        print(
            f"note: {n_before - len(book)} of {n_before} marks are not invertible (outside "
            "the BS price range at any vol) and are excluded from the decomposition."
        )

    lines = [
        f"Driver attribution, {args.book}-marked book.",
        f"Frozen spec: expanding pooled term gate q={Q:.2f}, market marks, MEGACAP_COST.",
        "Gross of costs. Positive = the leg made money for the short straddle.",
        "Vols inverted from the book's own marks, so the legs reconcile to realised P&L.",
    ]
    rows = _attribute(book, lines, f"GATED ({args.book}-marked)")
    print("\n".join(lines))

    existing = pd.read_csv(OUT) if OUT.exists() else pd.DataFrame()
    out = pd.DataFrame(rows)
    if not existing.empty:
        existing = existing[~existing["book"].isin(out["book"])]
        out = pd.concat([existing, out], ignore_index=True)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(OUT, index=False)
    print(f"\nwritten: {OUT.resolve()}")


if __name__ == "__main__":
    main()
