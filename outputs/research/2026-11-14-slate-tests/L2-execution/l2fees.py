"""
l2fees.py
Stock-hedge commission and delta-band helpers for the L2 lane (added after the B1 to B8 freezes,
so the frozen ``l2lib.py`` stays untouched).

Commission model (every figure from ``ExecutionLeversConfig``; the IB figures are recalled,
because Interactive Brokers' pages refuse automated clients): one marketable stock order per
nonzero rebalance, including the expiry residual. IBKR Pro Tiered charges USD 0.0035 per share,
at least USD 0.35 and at most 1% of the order's value, plus a USD 0.003 take fee and USD 0.0002
clearing per share. Fixed charges USD 0.005 per share, at least USD 1.00 and at most 1%. SEC
Section 31 and FINRA trading-activity fees on sales are not charged; ``sell_fee_bound`` sizes them
at the recalled rates in ``ExecutionLeversConfig`` so the omission is measured, not assumed.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import l2lib as L  # noqa: E402
import numpy as np  # noqa: E402

from earnings_iv_crush.config import EXECUTION_LEVERS as XL  # noqa: E402
from earnings_iv_crush.research import hedged_hold as hh  # noqa: E402


def order_prices(kw: dict) -> np.ndarray:
    """Price of each stock order: the hedging closes, then the settlement close."""
    return np.r_[np.asarray(kw["closes"], float), float(kw["settle_close"])]


def stock_commission(
    traded: np.ndarray, prices: np.ndarray, contracts: int, schedule: str = "tiered"
) -> tuple[float, int, int]:
    """USD per straddle-share, the number of orders, and how many hit the 1% cap."""
    sh = np.rint(100.0 * contracts * np.asarray(traded, float))
    px = np.asarray(prices, float)
    keep = sh >= 1
    sh, px = sh[keep], px[keep]
    per, mn = (
        (XL.stock_tiered_per_share, XL.stock_tiered_min_order)
        if schedule == "tiered"
        else (XL.stock_fixed_per_share, XL.stock_fixed_min_order)
    )
    cap = XL.stock_max_commission_frac * sh * px
    comm = np.minimum(np.maximum(sh * per, mn), cap)
    if schedule == "tiered":
        comm = comm + sh * (XL.stock_take_fee_per_share + XL.stock_clearing_per_share)
    n_cap = int((np.maximum(sh * per, mn) > cap).sum())
    return float(comm.sum() / (100.0 * contracts)), int(sh.size), n_cap


def traded_for(kw: dict, h: np.ndarray, signed: bool = False) -> np.ndarray:
    """Shares traded at each close and at settlement for a held sequence ``h`` (bought > 0)."""
    n = len(kw["closes"])
    ca, pa = kw.get("call_assigned_at"), kw.get("put_assigned_at")
    k, settle = float(kw["strike"]), float(kw["settle_close"])
    call_live, put_live, h_prev = True, True, 0.0
    out = np.zeros(n + 1)
    for i in range(n):
        delivered = 0.0
        if call_live and ca == i:
            call_live, delivered = False, delivered - 1.0
        if put_live and pa == i:
            put_live, delivered = False, delivered + 1.0
        out[i] = h[i] - (h_prev + delivered)
        h_prev = h[i]
    if call_live and put_live:
        sgn = float(np.sign(settle - k))
    else:
        sgn = float(call_live and settle > k) - float(put_live and settle < k)
    out[n] = sgn - h_prev
    return out if signed else np.abs(out)


def sell_fee_bound(kw: dict, h: np.ndarray, premium: float) -> float:
    """SEC Section 31 and FINRA TAF on every sale (stock sells and the option sale), USD/share."""
    t = traded_for(kw, h, signed=True)
    px = order_prices(kw)
    sold = np.where(t < 0, -t, 0.0)
    sec = XL.sec_fee_rate_bound * (float((sold * px).sum()) + float(premium))
    return sec + XL.finra_taf_per_share * float(sold.sum())


def banded(kw: dict, band: float) -> np.ndarray:
    """Black-Scholes targets, re-set after the first close only when the gap exceeds ``band``."""
    target, _ = L.hedge_sequence(kw)
    if band <= 0:
        return target
    n = target.size
    ca, pa = kw.get("call_assigned_at"), kw.get("put_assigned_at")
    h = np.zeros(n)
    h_prev = 0.0
    for i in range(n):
        delivered = (-1.0 if ca == i else 0.0) + (1.0 if pa == i else 0.0)
        pos = h_prev + delivered
        # As lane A's band: always set at the reaction close, then only beyond the band.
        h[i] = target[i] if (i == 0 or abs(target[i] - pos) > band) else pos
        h_prev = h[i]
    return h


def value_with_band(kw: dict, band: float, contracts: int) -> dict:
    """Net P&L (USD per share) of the banded hedge, before and after stock commission."""
    h = banded(kw, band)
    r = hh.hedged_short_straddle(**kw, hedge_ratios=h)
    t = traded_for(kw, h)
    comm, n_orders, n_cap = stock_commission(t, order_prices(kw), contracts)
    return {
        "net": r.net_pnl,
        "net_comm": r.net_pnl - comm,
        "comm": comm,
        "orders": n_orders,
        "capped": n_cap,
        "hedge": r.hedge_pnl,
        "equity_cost": r.equity_cost,
    }
