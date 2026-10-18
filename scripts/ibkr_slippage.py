"""ibkr_slippage.py: sample live option quoted slippage from the IBKR TWS API.

Measures the quoted bid/ask spread on the ATM straddle legs for a set of
underlyings and reports slippage in dollars and in implied-vol points. IBKR
serves no historical quotes for expired options, so this is a forward sampler:
run it at the time of day you would actually enter (e.g. near the close before
an earnings print) to characterise the slippage a short-vol earnings trade
would pay.

Implied vol is inverted locally from the quoted prices with Black-Scholes
rather than taken from IBKR's option-computation ticks, so it works on free
delayed data with no OPRA subscription. The absolute IV level carries a small
European/no-dividend approximation error, but that error is common-mode across
bid and ask and cancels in the bid-ask IV spread, which is the reported
slippage quantity.

Requires TWS or IB Gateway running with the API socket enabled
(Global Config > API > Settings: Enable ActiveX and Socket Clients).
Paper TWS defaults to port 7497; live TWS to 7496; Gateway to 4002/4001.
Without a live options-data subscription, pass --data-type 3 for delayed quotes.

Usage:
    python -m ibkr_slippage --symbols AAPL MSFT NVDA --dte 7 --data-type 3
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from datetime import date, datetime
from math import erf, exp, log, sqrt
from time import monotonic

from ib_async import IB, Option, Stock, Ticker

# ── config ──────────────────────────────────────────────────────────────────

DATA_TYPE_NAMES = {1: "live", 2: "frozen", 3: "delayed", 4: "delayed-frozen"}

# Continuously compounded annualised, ACT/365 (house convention).
DEFAULT_RATE = 0.043
DEFAULT_DIV_YIELD = 0.0


# ── Black-Scholes implied-vol inversion ─────────────────────────────────────


def _norm_cdf(x: float) -> float:
    return 0.5 * (1.0 + erf(x / sqrt(2.0)))


def _bs_price(
    spot: float, strike: float, t: float, r: float, q: float, sigma: float, right: str
) -> float:
    """European Black-Scholes price with continuous dividend yield q."""
    if sigma <= 0.0 or t <= 0.0:
        fwd_intrinsic = spot * exp(-q * t) - strike * exp(-r * t)
        return max(0.0, fwd_intrinsic if right == "C" else -fwd_intrinsic)
    vol_t = sigma * sqrt(t)
    d1 = (log(spot / strike) + (r - q + 0.5 * sigma * sigma) * t) / vol_t
    d2 = d1 - vol_t
    if right == "C":
        return spot * exp(-q * t) * _norm_cdf(d1) - strike * exp(-r * t) * _norm_cdf(d2)
    return strike * exp(-r * t) * _norm_cdf(-d2) - spot * exp(-q * t) * _norm_cdf(-d1)


def _implied_vol(
    price: float, spot: float, strike: float, t: float, r: float, q: float, right: str
) -> float | None:
    """Invert BS for implied vol by bisection; None if the price is off the arbitrage bounds."""
    if price <= 0.0 or spot <= 0.0 or t <= 0.0:
        return None
    lo, hi = 1e-4, 5.0
    p_lo = _bs_price(spot, strike, t, r, q, lo, right)
    p_hi = _bs_price(spot, strike, t, r, q, hi, right)
    if not (p_lo <= price <= p_hi):  # below intrinsic or above the cap, no solution
        return None
    for _ in range(100):
        mid = 0.5 * (lo + hi)
        if _bs_price(spot, strike, t, r, q, mid, right) < price:
            lo = mid
        else:
            hi = mid
        if hi - lo < 1e-6:
            break
    return 0.5 * (lo + hi)


# ── data model ──────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class LegQuote:
    """Quoted state of a single option leg, with locally inverted implied vols."""

    right: str  # "C" or "P"
    strike: float
    bid: float
    ask: float
    bid_iv: float | None
    ask_iv: float | None

    @property
    def mid(self) -> float | None:
        if self.bid > 0 and self.ask > 0:
            return 0.5 * (self.bid + self.ask)
        return None

    @property
    def spread(self) -> float | None:
        """Full quoted spread in dollars (round-trip cost, one leg)."""
        return (self.ask - self.bid) if self.mid is not None else None

    @property
    def spread_pct(self) -> float | None:
        m, s = self.mid, self.spread
        return (s / m) if (m and s is not None and m > 0) else None

    @property
    def iv_spread(self) -> float | None:
        """Full quoted spread in vol points (round-trip, one leg)."""
        if self.bid_iv is not None and self.ask_iv is not None:
            return self.ask_iv - self.bid_iv
        return None


# ── quote plumbing ──────────────────────────────────────────────────────────


def _wait_for(ib: IB, ticker: Ticker, timeout: float = 4.0) -> Ticker:
    """Block until a ticker has a two-sided quote or the timeout elapses."""
    deadline = monotonic() + timeout
    while monotonic() < deadline:
        ib.sleep(0.25)
        if ticker.bid == ticker.bid and ticker.ask == ticker.ask:  # not NaN
            if ticker.bid > 0 and ticker.ask > 0:
                break
    return ticker


def _underlying_price(ib: IB, stock: Stock) -> float | None:
    tkr = ib.reqMktData(stock, "", False, False)
    _wait_for(ib, tkr)
    px = tkr.marketPrice()
    if not (px == px) or px <= 0:  # NaN or non-positive
        px = tkr.close if (tkr.close == tkr.close) else None
    ib.cancelMktData(stock)
    return px


def _pick_expiry(expirations: list[str], target_dte: int) -> str | None:
    """Nearest listed expiry on or after today+target_dte; else the nearest one."""
    today = date.today()
    dated = sorted(datetime.strptime(e, "%Y%m%d").date() for e in expirations)
    forward = [e for e in dated if (e - today).days >= target_dte]
    chosen = forward[0] if forward else (dated[-1] if dated else None)
    return chosen.strftime("%Y%m%d") if chosen else None


def _leg_prices(ib: IB, opt: Option) -> tuple[float, float]:
    """Return (bid, ask) for one option leg; zeros where a side is missing."""
    tkr = ib.reqMktData(opt, "", False, False)
    _wait_for(ib, tkr)
    # IBKR returns -1 when no quote is available; treat any non-positive as missing.
    bid = tkr.bid if (tkr.bid == tkr.bid and tkr.bid > 0) else 0.0
    ask = tkr.ask if (tkr.ask == tkr.ask and tkr.ask > 0) else 0.0
    ib.cancelMktData(opt)
    return bid, ask


def sample_straddle(
    ib: IB, symbol: str, target_dte: int, r: float, q: float
) -> tuple[str, float, float, list[LegQuote]] | None:
    """Return (expiry, strike, spot, [call, put]) for the ATM straddle, or None if unresolved."""
    stock = Stock(symbol, "SMART", "USD")
    if not ib.qualifyContracts(stock):
        print(f"  {symbol}: could not qualify underlying - skipped")
        return None

    spot = _underlying_price(ib, stock)
    if spot is None:
        print(f"  {symbol}: no underlying price (market closed / no subscription) - skipped")
        return None

    chains = ib.reqSecDefOptParams(stock.symbol, "", stock.secType, stock.conId)
    smart = next((c for c in chains if c.exchange == "SMART"), None)
    if smart is None:
        print(f"  {symbol}: no SMART option chain - skipped")
        return None

    expiry = _pick_expiry(list(smart.expirations), target_dte)
    if expiry is None:
        print(f"  {symbol}: no listed expiries - skipped")
        return None

    strikes = sorted(smart.strikes, key=lambda k: abs(k - spot))
    if not strikes:
        print(f"  {symbol}: no listed strikes - skipped")
        return None
    strike = strikes[0]

    legs = [
        Option(symbol, expiry, strike, right, "SMART", tradingClass=smart.tradingClass)
        for right in ("C", "P")
    ]
    qualified = ib.qualifyContracts(*legs)
    if len(qualified) != 2:
        print(f"  {symbol}: could not qualify {expiry} {strike} straddle - skipped")
        return None

    t = (datetime.strptime(expiry, "%Y%m%d").date() - date.today()).days / 365.0
    quotes: list[LegQuote] = []
    for opt in qualified:
        bid, ask = _leg_prices(ib, opt)
        quotes.append(
            LegQuote(
                right=opt.right,
                strike=strike,
                bid=bid,
                ask=ask,
                bid_iv=_implied_vol(bid, spot, strike, t, r, q, opt.right),
                ask_iv=_implied_vol(ask, spot, strike, t, r, q, opt.right),
            )
        )
    return expiry, strike, spot, quotes


# ── reporting ───────────────────────────────────────────────────────────────


def _fmt(x: float | None, spec: str) -> str:
    return format(x, spec) if x is not None else "   n/a"


def report(rows: list[tuple[str, str, float, float, list[LegQuote]]]) -> None:
    print()
    hdr = (
        f"{'sym':<6}{'spot':>9}  {'expiry':<11}{'strike':>8}{'leg':>4}"
        f"{'bid':>9}{'ask':>9}{'mid':>9}{'spr$':>8}{'spr%':>7}"
        f"{'bidIV':>8}{'askIV':>8}{'IVspr':>8}"
    )
    print(hdr)
    print("-" * len(hdr))
    for sym, expiry, strike, spot, quotes in rows:
        for i, quote in enumerate(quotes):
            lead = f"{sym:<6}{spot:>9.2f}  " if i == 0 else f"{'':<6}{'':>9}  "
            print(
                f"{lead}{expiry:<11}{strike:>8.2f}{quote.right:>4}"
                f"{quote.bid:>9.2f}{quote.ask:>9.2f}{_fmt(quote.mid, '>9.2f')}"
                f"{_fmt(quote.spread, '>8.2f')}{_fmt(quote.spread_pct, '>7.1%')}"
                f"{_fmt(quote.bid_iv, '>8.1%')}{_fmt(quote.ask_iv, '>8.1%')}"
                f"{_fmt(quote.iv_spread, '>8.1%')}"
            )
        # Round-trip = full spread on both legs; single-side entry = half of that.
        dollar_rt = sum(q.spread for q in quotes if q.spread is not None)
        iv_rts = [q.iv_spread for q in quotes if q.iv_spread is not None]
        iv_rt = sum(iv_rts) if len(iv_rts) == len(quotes) else None
        line = f"{'':<15}{'straddle':<11}{'':>12}  round-trip: ${dollar_rt:.2f}"
        if iv_rt is not None:
            line += f"   {iv_rt * 100:.1f} vol pts   (entry ~ {iv_rt * 50:.1f} vol pts)"
        else:
            line += "   vol pts: n/a (one-sided or off-bounds quote)"
        print(line)
        print()


# ── entry point ─────────────────────────────────────────────────────────────


def main() -> None:
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    p.add_argument("--symbols", nargs="+", required=True, help="underlying tickers")
    p.add_argument(
        "--dte", type=int, default=7, help="target days to expiry for the straddle (default 7)"
    )
    p.add_argument(
        "--port", type=int, default=7497, help="TWS/Gateway socket port (paper TWS 7497)"
    )
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--client-id", type=int, default=17)
    p.add_argument("--rate", type=float, default=DEFAULT_RATE, help="cc annualised rate, ACT/365")
    p.add_argument(
        "--div-yield", type=float, default=DEFAULT_DIV_YIELD, help="continuous dividend yield"
    )
    p.add_argument(
        "--data-type",
        type=int,
        default=1,
        choices=(1, 2, 3, 4),
        help="1 live, 2 frozen, 3 delayed, 4 delayed-frozen (default 1; use 3 if unsubscribed)",
    )
    args = p.parse_args()

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")  # Windows console defaults to cp1252

    ib = IB()
    ib.connect(args.host, args.port, clientId=args.client_id)
    ib.reqMarketDataType(args.data_type)
    print(f"connected to {args.host}:{args.port}  data={DATA_TYPE_NAMES[args.data_type]}")

    rows: list[tuple[str, str, float, float, list[LegQuote]]] = []
    try:
        for sym in args.symbols:
            res = sample_straddle(ib, sym.upper(), args.dte, args.rate, args.div_yield)
            if res is not None:
                expiry, strike, spot, quotes = res
                rows.append((sym.upper(), expiry, strike, spot, quotes))
    finally:
        if rows:
            report(rows)
        ib.disconnect()


if __name__ == "__main__":
    main()
