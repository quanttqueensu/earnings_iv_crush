"""
shadow_book.py
Mark the shadow alternatives beside every closed paper trade and write the shadow book.

Read-only on the paper book's stores; never connects to a broker. Stock paths for the hedged
shadow come from Yahoo Finance daily bars (free). The output is a derived report, rebuilt in
full on every run, written next to the pass's other stores.

Usage
-----
    python -m scripts.shadow_book            # transmitting stores
    python -m scripts.shadow_book --dry      # dry stores
"""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from earnings_iv_crush.config import SHADOW
from earnings_iv_crush.live import shadow
from earnings_iv_crush.live.session import Stores
from scripts.paper_trade_ibkr import exchange_today


def yahoo_path(ticker: str, start: pd.Timestamp, end: pd.Timestamp) -> pd.DataFrame | None:
    """As-traded closes, total returns and the split factor from Yahoo daily bars."""
    import yfinance as yf

    g = yf.Ticker(ticker).history(
        start=(start - pd.Timedelta(days=7)).date(),
        end=(end + pd.Timedelta(days=1)).date(),
        auto_adjust=False,
        actions=True,
    )
    if g is None or g.empty:
        print(f"  {ticker}: no Yahoo bars")
        return None
    g.index = pd.to_datetime(g.index).tz_localize(None).normalize()
    sp = g.get("Stock Splits", pd.Series(0.0, index=g.index)).replace(0.0, 1.0).fillna(1.0)
    after = sp[::-1].cumprod()[::-1].shift(-1).fillna(1.0)
    return pd.DataFrame(
        {"prc": g["Close"] * after, "ret": g["Adj Close"].pct_change(), "cfacpr": after}
    )


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dry", action="store_true", help="read the dry stores instead")
    args = ap.parse_args(argv)
    stores = Stores.for_mode(transmit=not args.dry)
    trades = shadow.closed_trades(
        stores.open_positions, stores.nostop, stores.reconciliation, transmitted_only=not args.dry
    )
    book = shadow.build_shadow(trades, yahoo_path, exchange_today())
    out = Path(stores.nostop).parent / SHADOW.out_name
    out.parent.mkdir(parents=True, exist_ok=True)
    book.to_csv(out, index=False)
    print(shadow.summary(book))
    print(f"written {out}")


if __name__ == "__main__":
    main()
