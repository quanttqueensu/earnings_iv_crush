"""
span_straddle_example.py
Illustrative SPAN-style margin for a one-lot short ATM futures-option straddle.

The only verified input is the outright futures maintenance margin IB publishes for each root
(https://www.interactivebrokers.com/en/trading/margin-futures-fops.php, US resident, read
2026-11-13). Under classic SPAN the outright maintenance margin of one future equals the price
scan range (PSR) for that product, so it is used here as the PSR. Futures price, implied
volatility, the volatility scan range (VSR) and the extreme-move convention are NOT published by
IB and are illustrative inputs (conjecture), swept so the reader sees the sensitivity.

This is not the broker's number. CME has moved energy and equity products to SPAN 2 (historical
VaR), so this calculation does not apply to NG or CL, and IB may add house margin on top of the
exchange figure. The trading harness must read the real figure from a what-if order.

Usage
-----
    python scripts/span_straddle_example.py > logs/span_example.log

References
----------
CME Group, "SPAN Methodology Overview" (16 risk scenarios: price moves of 0, 1/3, 2/3 and 3/3 of
the PSR with volatility up and down, plus two extreme moves covered at a fraction).
Black, F. (1976). The pricing of commodity contracts. Journal of Financial Economics 3, 167-179.
"""

from __future__ import annotations

import itertools
import math

from scipy.stats import norm

# ── verified inputs: IB overnight maintenance margin per outright future, USD ──
IB_MAINT_USD = {"ZC": 1557.28, "ZN": 1988.47, "ZS": 3940.74, "HE": 1835.42}

# ── illustrative inputs (conjecture): price, unit multiplier, ATM vol ──
PRODUCTS = {
    # root: (futures price, USD per 1.00 price unit, ATM implied vol)
    "ZC": (4.40, 5_000.0, 0.24),  # USD per bushel, 5,000 bu
    "ZS": (10.50, 5_000.0, 0.18),  # USD per bushel, 5,000 bu
    "ZN": (112.0, 1_000.0, 0.050),  # points, USD 1,000 per point
    "HE": (0.85, 40_000.0, 0.25),  # USD per lb, 40,000 lb
}
RATE = 0.04  # continuously compounded, ACT/365; second-order for these tenors
TENORS_DAYS = (7, 30)
VSR_GRID = (0.03, 0.06, 0.10)  # absolute vol change in the scan scenarios
EXTREME = ((3.0, 0.33), (2.0, 0.35))  # (multiple of PSR, fraction of loss covered): both seen


def black76(f: float, k: float, t: float, r: float, sigma: float, right: str) -> float:
    """Black-76 price of a European futures option, per unit of the futures price."""
    if t <= 0 or sigma <= 0:
        return max(f - k, 0.0) if right == "C" else max(k - f, 0.0)
    d1 = (math.log(f / k) + 0.5 * sigma**2 * t) / (sigma * math.sqrt(t))
    d2 = d1 - sigma * math.sqrt(t)
    df = math.exp(-r * t)
    if right == "C":
        return df * (f * norm.cdf(d1) - k * norm.cdf(d2))
    return df * (k * norm.cdf(-d2) - f * norm.cdf(-d1))


def straddle(f: float, k: float, t: float, sigma: float) -> float:
    return black76(f, k, t, RATE, sigma, "C") + black76(f, k, t, RATE, sigma, "P")


def span_risk(root: str, days: int, vsr: float, extreme: tuple[float, float]) -> dict:
    """Worst one-day scenario loss of a short one-lot ATM straddle, USD."""
    f0, mult, sig = PRODUCTS[root]
    psr_units = IB_MAINT_USD[root] / mult  # price scan range in price units
    t0 = days / 365.0
    t1 = max(days - 1, 0) / 365.0  # SPAN scenarios are one day forward
    v0 = straddle(f0, f0, t0, sig)
    losses = []
    for frac, dv in itertools.product((0.0, 1 / 3, 2 / 3, 1.0, -1 / 3, -2 / 3, -1.0), (vsr, -vsr)):
        v = straddle(f0 + frac * psr_units, f0, t1, max(sig + dv, 1e-4))
        losses.append((v - v0) * mult)
    mx, cover = extreme
    for sgn in (1.0, -1.0):
        v = straddle(f0 + sgn * mx * psr_units, f0, t1, sig)
        losses.append(cover * (v - v0) * mult)
    risk = max(losses)
    notional = f0 * mult
    return {
        "premium_usd": v0 * mult,
        "scan_risk_usd": risk,
        "harness_regt_model_usd": 0.20 * notional + v0 * mult,
        "notional_usd": notional,
    }


def main() -> None:
    print("Illustrative SPAN-style requirement, one-lot short ATM straddle (USD, per straddle).")
    print("PSR = IB overnight maintenance margin of the outright future (verified 2026-11-13);")
    print("price, vol, VSR and extreme-move convention are illustrative (conjecture).\n")
    hdr = (
        f"{'root':<4} {'days':>4} {'VSR':>5} {'extreme':>9} {'premium':>9} "
        f"{'scan_risk':>10} {'risk/prem':>9} {'regt_model':>10}"
    )
    print(hdr)
    for root, days, vsr, ext in itertools.product(PRODUCTS, TENORS_DAYS, VSR_GRID, EXTREME):
        r = span_risk(root, days, vsr, ext)
        print(
            f"{root:<4} {days:>4} {vsr:>5.2f} {ext[0]:>4.0f}x{ext[1]:.2f} "
            f"{r['premium_usd']:>9.0f} {r['scan_risk_usd']:>10.0f} "
            f"{r['scan_risk_usd'] / r['premium_usd']:>9.2f} {r['harness_regt_model_usd']:>10.0f}"
        )


if __name__ == "__main__":
    main()
