"""
ib_margin_probe.py
Check the modelled Reg-T margin against the margin a broker actually charges.

Every return-on-margin figure in this project divides by ``regt_straddle_margin``
(``engine/pnl.py``), a modelled Reg-T formula::

    margin_per_share = 0.20 * spot + premium_per_share

That denominator carries the load in the central claim about the term gate: the
gate's apparent per-trade edge is a *leverage* effect, because margin scales with
**spot** while the credit collected scales with **implied vol**, so gated (high-IV)
events collect more premium against a margin base that has barely moved.

The untested weakness in that argument is the formula itself. Brokers do not margin
a high-vol name like a quiet one - they stress it harder. If the true margin on a
pre-earnings straddle exceeds ``0.20 * spot + premium``, then the modelled
denominator is *understated exactly on the gated events*, and the gate's remaining
apparent benefit is partly an artefact of the margin model rather than of leverage.

IB answers this for free. A ``whatIf`` order is priced by the broker's real margin
engine and returned as a preview; it is **never transmitted** and never reaches a
book. This script prices a short ATM straddle on each name and reports IB's initial
margin and commission against the modelled figures.

Requires the TWS "Read-Only API" box **unticked** (Configure > API > Settings): IB
routes ``whatIf`` through the order path, so read-only rejects it. Nothing is
transmitted regardless - every order carries ``whatIf=True``, and the paper-port
guard in ``live/ib_connection.py`` refuses any live port.

Usage::

    python scripts/ib_margin_probe.py
    python scripts/ib_margin_probe.py --ticker JPM --ticker GS
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from earnings_iv_crush.config import LIVE  # noqa: E402
from earnings_iv_crush.engine.pnl import COST_PER_CONTRACT, regt_straddle_margin  # noqa: E402
from earnings_iv_crush.live.ib_connection import connect_paper  # noqa: E402

DEFAULT_BASKET = ("JPM", "GS", "C", "WFC", "BAC", "MS")
CONTRACTS = 1  # one straddle: 1 short call + 1 short put, 100 shares each
SETTLE_SECONDS = 6.0
OUT_CSV = Path("outputs/research/ib_margin_probe.csv")


def _clean(px: float | None) -> float:
    if px is None or not np.isfinite(px) or px < 0:
        return float("nan")
    return float(px)


def probe(ib, ticker: str) -> dict | None:
    """Price a short ATM straddle through IB's margin engine (whatIf, never sent)."""
    from ib_async import Option, Order, Stock

    qualified = ib.qualifyContracts(Stock(ticker.replace("-", " "), "SMART", "USD"))
    if not qualified:
        return None
    stock = qualified[0]

    stk = ib.reqMktData(stock, "", False, False)
    ib.sleep(SETTLE_SECONDS)
    spot = next(
        (float(p) for p in (stk.last, stk.close) if p is not None and np.isfinite(p) and p > 0),
        float("nan"),
    )
    ib.cancelMktData(stock)
    if not np.isfinite(spot):
        return None

    params = ib.reqSecDefOptParams(stock.symbol, "", "STK", stock.conId)
    smart = [p for p in params if p.exchange == "SMART"] or list(params)
    today = pd.Timestamp.today().normalize()
    expiries = sorted({e for p in smart for e in p.expirations if pd.Timestamp(e) > today})
    strikes = sorted({k for p in smart for k in p.strikes})
    if not expiries or not strikes:
        return None
    expiry = expiries[0]
    strike = min(strikes, key=lambda k: abs(k - spot))

    legs = ib.qualifyContracts(
        Option(stock.symbol, expiry, strike, "C", "SMART"),
        Option(stock.symbol, expiry, strike, "P", "SMART"),
    )
    if len(legs) != 2:
        return None

    ticks = [ib.reqMktData(c, "", False, False) for c in legs]
    ib.sleep(SETTLE_SECONDS)
    credit_ps = 0.0
    for t in ticks:
        bid, ask = _clean(t.bid), _clean(t.ask)
        if not (np.isfinite(bid) and np.isfinite(ask)):
            for c in legs:
                ib.cancelMktData(c)
            return None
        credit_ps += 0.5 * (bid + ask)

    def _f(x: object) -> float:
        try:
            v = float(x)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            return float("nan")
        return float("nan") if abs(v) > 1e100 else v  # IB sends DBL_MAX for "unknown"

    # A BAG combo would let IB margin the straddle as one position, but the paper
    # account rejects it ("riskless combination orders are not allowed"), so each
    # short leg is priced on its own and the two are combined by the Reg-T straddle
    # rule: charge the greater side's requirement, plus the market value of the
    # other side (which cannot be exercised against you at the same time).
    per_leg: dict[str, float] = {}
    leg_mid: dict[str, float] = {}
    for c, t in zip(legs, ticks, strict=True):
        mid = 0.5 * (_clean(t.bid) + _clean(t.ask))
        order = Order(
            action="SELL",
            orderType="LMT",
            totalQuantity=CONTRACTS,
            lmtPrice=round(mid, 2),
            tif="DAY",
            whatIf=True,
        )
        st = ib.whatIfOrder(c, order)
        if st is None or not getattr(st, "initMarginChange", ""):
            return None
        per_leg[c.right[0]] = abs(_f(st.initMarginChange))
        leg_mid[c.right[0]] = mid
        ib_comm_max = _f(getattr(st, "maxCommission", "nan"))

    heavy = max(per_leg, key=lambda r: per_leg[r])
    light = "P" if heavy == "C" else "C"
    ib_init = per_leg[heavy] + leg_mid[light] * 100 * CONTRACTS

    modelled = regt_straddle_margin(spot, strike, credit_ps, CONTRACTS)
    modelled_comm = COST_PER_CONTRACT * 2 * CONTRACTS  # two legs, one fill each

    return {
        "ticker": ticker,
        "spot": spot,
        "expiry": expiry,
        "strike": strike,
        "credit_per_share": credit_ps,
        "implied_move": credit_ps / spot,
        "ib_call_margin": per_leg.get("C", np.nan),
        "ib_put_margin": per_leg.get("P", np.nan),
        "modelled_margin": modelled,
        "ib_init_margin": ib_init,
        "margin_ratio": ib_init / modelled if modelled else np.nan,
        "modelled_commission": modelled_comm,
        "ib_commission_max": ib_comm_max * 2 * CONTRACTS,
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--ticker", action="append")
    ap.add_argument("--port", type=int, default=LIVE.ib_paper_port)
    ap.add_argument("--client-id", type=int, default=LIVE.ib_client_id + 2)
    ap.add_argument("--data-type", type=int, default=3)
    args = ap.parse_args()
    tickers = tuple(args.ticker) if args.ticker else DEFAULT_BASKET

    try:
        ib = connect_paper(port=args.port, client_id=args.client_id)
    except Exception as exc:
        print(f"could not reach a paper gateway on 127.0.0.1:{args.port} - {exc}")
        return
    ib.reqMarketDataType(args.data_type)

    rows: list[dict] = []
    try:
        for t in tickers:
            r = probe(ib, t)
            if r is None:
                print(f"{t:6s} no margin preview (read-only API still on, or no quote?)")
                continue
            rows.append(r)
            print(
                f"{t:6s} spot {r['spot']:8.2f}  K {r['strike']:8.1f}  "
                f"credit {r['credit_per_share']:6.2f} ({r['implied_move']:5.2%})  "
                f"modelled ${r['modelled_margin']:8,.0f}  IB ${r['ib_init_margin']:8,.0f}  "
                f"{r['margin_ratio']:5.2f}x   comm IB ${r['ib_commission_max']:.2f} "
                f"vs modelled ${r['modelled_commission']:.2f}"
            )
    finally:
        ib.disconnect()

    if not rows:
        print(
            "\nNo previews returned. If every name failed, untick "
            "Configure > API > Settings > Read-Only API in TWS and re-run. "
            "Nothing is transmitted: every order carries whatIf=True."
        )
        return

    df = pd.DataFrame(rows)
    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(OUT_CSV, index=False)
    print(
        f"\nIB initial margin / modelled Reg-T: median {df['margin_ratio'].median():.2f}x  "
        f"range [{df['margin_ratio'].min():.2f}x, {df['margin_ratio'].max():.2f}x]"
    )
    print(
        "If this is materially above 1.0x, every return-on-margin figure in the "
        "project is overstated, and most so on the high-IV events the gate selects."
    )
    print(f"\nwrote {OUT_CSV}")


if __name__ == "__main__":
    main()
