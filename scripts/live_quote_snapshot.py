"""
live_quote_snapshot.py
Snapshot live IBKR paper-account quotes on megacap straddles and price the quoted
width the two competing ways, so the backtest's cost model can be checked against a
broker quote rather than against vendor marks.

The backtest's break-even rests on one number: the round-trip quoted width as a
fraction of the credit collected. ``scripts/build/measure_spread.py`` estimates it by
averaging the two legs' *relative* spreads with equal weight. That estimator is
unbiased only when the legs cost about the same. At entry they do. At exit they do
not: after an earnings gap one leg is intrinsic-heavy and one is a near-worthless
tail, so an equal weighting loads most of the average onto the leg being closed for
pennies, and the estimator diverges from the price of unwinding the package.

Per leg, on the touch::

    dollar width  w_i = ask_i - bid_i
    mid           m_i = (ask_i + bid_i) / 2

    mean-of-ratios   (measure_spread.py:185)   = mean_i ( w_i / m_i )
    dollar-weighted  (what unwinding costs)    = sum_i w_i / sum_i m_i

The two coincide when the legs are of similar value and separate as they diverge.
Rather than assert an exit moneyness, this script walks a **ladder** of strikes
displaced from spot (0 to 8%, roughly the range an earnings gap spans) and prints
both estimators at each rung. The ATM rung is the control: the estimators must agree
there. Divergence further out is the estimator, not the market.

Market data: a paper account without an OPRA subscription serves *delayed* quotes.
That is sufficient here. A delayed quote is still two-sided, so its **width** is a
real measurement even though its **level** is fifteen minutes stale, and width is the
only quantity this script exists to read. The feed actually used is printed.

Streaming (``reqMktData``) is used rather than snapshot (``reqTickers``): delayed
ticks arrive too slowly for the snapshot call, which returns empty.

Nothing is ordered. This is a read-only market-data request.

Usage::

    python scripts/live_quote_snapshot.py
    python scripts/live_quote_snapshot.py --ticker AAPL --ticker NVDA
    python scripts/live_quote_snapshot.py --port 4002        # IB Gateway paper
    python scripts/live_quote_snapshot.py --data-type 1      # if OPRA-entitled
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from earnings_iv_crush.config import LIVE  # noqa: E402
from earnings_iv_crush.live.ib_connection import connect_paper  # noqa: E402

# The most liquid weeklies in the strategy's own 45-name universe: the width measured
# here is therefore the *best* case the strategy could ever hope to trade against.
DEFAULT_BASKET = ("AAPL", "MSFT", "NVDA", "AMZN", "META")

# Strike displacements from spot, as a fraction. 0.0 is the entry (ATM) geometry;
# the upper rungs bracket the range an earnings gap actually lands in.
DISPLACEMENTS = (0.00, 0.02, 0.04, 0.06, 0.08)

MKT_DATA_MODES = {1: "live", 2: "frozen", 3: "delayed", 4: "delayed-frozen"}
SETTLE_SECONDS = 6.0  # delayed ticks need a few seconds to populate
OUT_CSV = Path("outputs/research/live_quoted_width.csv")


def _clean(px: float | None) -> float:
    """IB encodes 'no quote' as -1 or None; normalise both to NaN."""
    if px is None or not np.isfinite(px) or px < 0:
        return float("nan")
    return float(px)


def _spot(ib, stock) -> float:
    """Stream the underlying and take the first finite of last, close, midpoint."""
    tick = ib.reqMktData(stock, "", False, False)
    ib.sleep(SETTLE_SECONDS)
    px = next(
        (
            float(p)
            for p in (tick.last, tick.close, tick.marketPrice())
            if p is not None and np.isfinite(p) and p > 0
        ),
        float("nan"),
    )
    ib.cancelMktData(stock)
    return px


def snapshot(ib, ticker: str) -> list[dict]:
    """Quote a displacement ladder of straddles on the front expiry for one name."""
    from ib_async import Option, Stock

    qualified = ib.qualifyContracts(Stock(ticker.replace("-", " "), "SMART", "USD"))
    if not qualified:
        print(f"{ticker:6s} could not qualify underlying")
        return []
    stock = qualified[0]

    spot = _spot(ib, stock)
    if not np.isfinite(spot) or spot <= 0:
        print(f"{ticker:6s} no usable spot")
        return []

    params = ib.reqSecDefOptParams(stock.symbol, "", "STK", stock.conId)
    smart = [p for p in params if p.exchange == "SMART"] or list(params)
    today = pd.Timestamp.today().normalize()
    expiries = sorted({e for p in smart for e in p.expirations if pd.Timestamp(e) > today})
    all_strikes = sorted({k for p in smart for k in p.strikes})
    if not expiries or not all_strikes:
        print(f"{ticker:6s} no expiries/strikes")
        return []
    expiry = expiries[0]  # the front weekly: the expiry the strategy sells
    dte = (pd.Timestamp(expiry) - today).days

    # One strike per rung of the ladder, de-duplicated (coarse strike grids can
    # collapse two rungs onto the same listed strike).
    rungs: dict[float, float] = {}
    for d in DISPLACEMENTS:
        k = min(all_strikes, key=lambda k: abs(k - spot * (1.0 + d)))
        rungs.setdefault(k, d)

    contracts = [Option(stock.symbol, expiry, k, r, "SMART") for k in rungs for r in ("C", "P")]
    live = [c for c in ib.qualifyContracts(*contracts) if getattr(c, "conId", 0)]
    if not live:
        print(f"{ticker:6s} no contracts resolved on {expiry}")
        return []

    ticks = [ib.reqMktData(c, "", False, False) for c in live]
    ib.sleep(SETTLE_SECONDS)
    quotes: dict[tuple[float, str], tuple[float, float]] = {}
    for c, t in zip(live, ticks, strict=True):
        quotes[(float(c.strike), c.right[0])] = (_clean(t.bid), _clean(t.ask))
    for c in live:
        ib.cancelMktData(c)

    # The ATM package mid is the credit the strategy actually collects at entry, and
    # is therefore the correct denominator for every cost figure below. On an expiry
    # containing an earnings print it is the *earnings* credit; on a quiet week it is
    # not, and cost-as-a-fraction-of-credit read off such a week means nothing.
    k_atm = min(rungs, key=lambda k: rungs[k])
    cb, ca = quotes.get((k_atm, "C"), (np.nan, np.nan))
    pb, pa = quotes.get((k_atm, "P"), (np.nan, np.nan))
    credit = 0.5 * (ca + cb) + 0.5 * (pa + pb)
    implied_move = credit / spot if np.isfinite(credit) else float("nan")

    print(f"\n=== {ticker}   spot {spot:,.2f}   front expiry {expiry} ({dte}d)   ===")
    print(f"    ATM credit {credit:.2f}  ->  implied move {implied_move:.2%} of spot")
    print(
        f"{'displaced':>9s} {'strike':>8s} {'call bid/ask':>15s} {'put bid/ask':>15s} "
        f"{'pkg mid':>8s} {'pkg $w':>7s} {'$-wtd':>7s} {'mean-rat':>9s} {'ratio':>6s} "
        f"{'$w/credit':>10s}"
    )

    rows: list[dict] = []
    for k, d in sorted(rungs.items(), key=lambda kv: kv[1]):
        cb, ca = quotes.get((k, "C"), (np.nan, np.nan))
        pb, pa = quotes.get((k, "P"), (np.nan, np.nan))
        if not all(np.isfinite(x) for x in (cb, ca, pb, pa)):
            print(f"{d:8.0%}  {k:8.1f}  no two-sided quote")
            continue
        cw, pw = ca - cb, pa - pb
        cm, pm = 0.5 * (ca + cb), 0.5 * (pa + pb)
        if cm <= 0 or pm <= 0:
            print(f"{d:8.0%}  {k:8.1f}  zero mid")
            continue
        pkg_mid, pkg_w = cm + pm, cw + pw
        dollar_wtd = pkg_w / pkg_mid
        mean_rat = float(np.mean([cw / cm, pw / pm]))
        # The quantity the strategy's break-even is actually stated in: the dollar
        # width paid to unwind, over the credit taken in at entry.
        w_over_credit = pkg_w / credit if np.isfinite(credit) and credit > 0 else float("nan")
        print(
            f"{d:8.0%}  {k:8.1f} {cb:6.2f}/{ca:<8.2f} {pb:6.2f}/{pa:<8.2f} "
            f"{pkg_mid:8.2f} {pkg_w:7.2f} {dollar_wtd:7.2%} {mean_rat:9.2%} "
            f"{mean_rat / dollar_wtd:5.2f}x {w_over_credit:10.2%}"
        )
        rows.append(
            {
                "ticker": ticker,
                "spot": spot,
                "expiry": expiry,
                "dte": dte,
                "credit": credit,
                "implied_move": implied_move,
                "displacement": d,
                "strike": k,
                "call_bid": cb,
                "call_ask": ca,
                "put_bid": pb,
                "put_ask": pa,
                "pkg_mid": pkg_mid,
                "pkg_width": pkg_w,
                "dollar_weighted": dollar_wtd,
                "mean_of_ratios": mean_rat,
                "inflation": mean_rat / dollar_wtd,
                "width_over_credit": w_over_credit,
            }
        )
    return rows


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--ticker", action="append", help="repeatable; defaults to the megacap basket")
    ap.add_argument("--port", type=int, default=LIVE.ib_paper_port, help="7497 TWS / 4002 Gateway")
    ap.add_argument("--client-id", type=int, default=LIVE.ib_client_id + 1)
    ap.add_argument(
        "--data-type",
        type=int,
        default=3,
        choices=sorted(MKT_DATA_MODES),
        help="1 live (needs an OPRA entitlement), 3 delayed, 4 delayed-frozen",
    )
    args = ap.parse_args()
    tickers = tuple(args.ticker) if args.ticker else DEFAULT_BASKET

    try:
        ib = connect_paper(port=args.port, client_id=args.client_id)
    except Exception as exc:
        print(f"could not reach a paper gateway on 127.0.0.1:{args.port} - {exc}")
        print("Start TWS/IB Gateway (paper), API > Settings > Enable ActiveX and Socket Clients.")
        return

    ib.reqMarketDataType(args.data_type)
    print(f"market data type: {args.data_type} ({MKT_DATA_MODES[args.data_type]})")
    print(f"as of: {pd.Timestamp.now(tz='America/New_York'):%Y-%m-%d %H:%M:%S %Z}")

    rows: list[dict] = []
    try:
        for t in tickers:
            rows.extend(snapshot(ib, t))
    finally:
        ib.disconnect()

    if not rows:
        print("\nno two-sided quotes resolved.")
        return

    df = pd.DataFrame(rows)
    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(OUT_CSV, index=False)

    print("\n--- pooled across the basket: quoted width by strike displacement ---")
    print(
        f"{'displaced':>9s} {'n':>3s} {'$-weighted':>11s} {'mean-of-ratios':>15s} "
        f"{'inflation':>10s} {'$w/credit':>10s}"
    )
    for d, g in df.groupby("displacement"):
        print(
            f"{d:8.0%}  {len(g):3d} {g['dollar_weighted'].median():11.2%} "
            f"{g['mean_of_ratios'].median():15.2%} {g['inflation'].median():9.2f}x "
            f"{g['width_over_credit'].median():10.2%}"
        )
    print(f"\nwrote {OUT_CSV}")


if __name__ == "__main__":
    main()
