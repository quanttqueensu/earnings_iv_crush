"""
n10lib.py
Shared valuation for lane N10: a short ATM straddle on one Deribit expiry, entered at the last
marks before an entry time less the measured seller's discount, held to expiry and settled at
the Deribit delivery price. Same fill estimate as the closed Deribit macro study
(research/other_markets/research_deribit_macro.py); differences are listed in ``straddle``.

References
----------
Weiss et al. (2026), Bitcoin option expiration, gamma exposure, and intraday price reversals,
Finance Research Letters 107, 110340.
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
sys.path.insert(0, str(ROOT))

from earnings_iv_crush.research.protocol import date_clustered_ci  # noqa: E402

CACHE = HERE / "cache"


# ── config ───────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class N10Config:
    # Deribit instruments API taker_commission, verified 2026-11-13
    taker_fee_underlying: float = 0.0003
    # Deribit fee cap as a share of the option price (recalled from third-party fee summaries)
    fee_cap_share: float = 0.125
    # settlement fee on the in-the-money leg (recalled, applied as the conservative choice)
    settle_fee_underlying: float = 0.00015
    # minimum taker sells on the expiry to estimate the seller's discount (closed study value)
    min_sell_trades: int = 5
    window: pd.Timedelta = pd.Timedelta(hours=4)
    k_atm: float = float(np.sqrt(2 / np.pi))


CFG = N10Config()


# ── data ─────────────────────────────────────────────────────────────────────


def delivery_prices(index_name: str) -> pd.Series:
    d = pd.DataFrame(json.loads((CACHE / f"delivery_{index_name}.json").read_text()))
    return pd.Series(d["delivery_price"].to_numpy(), index=pd.to_datetime(d["date"]).dt.date)


def load_window(ccy: str, end: pd.Timestamp) -> pd.DataFrame:
    f = CACHE / f"{ccy}_trades_{end:%Y%m%dT%H%M}.parquet"
    if not f.exists():
        raise FileNotFoundError(f"window not pulled: {f.name}")
    df = pd.read_parquet(f)
    if df.empty:
        return df
    p = df["instrument_name"].str.split("-", expand=True)
    df = df.assign(
        expiry=pd.to_datetime(p[1], format="%d%b%y", errors="coerce").dt.tz_localize("UTC")
        + pd.Timedelta(hours=8),
        strike=pd.to_numeric(p[2], errors="coerce"),
        right=p[3],
        ts=pd.to_datetime(df["timestamp"], unit="ms", utc=True),
    )
    return df.dropna(subset=["expiry", "strike"])


# ── valuation ────────────────────────────────────────────────────────────────


def straddle(
    ccy: str,
    entry: pd.Timestamp,
    deliv: pd.Series,
    expiry: pd.Timestamp | None = None,
    after: pd.Timestamp | None = None,
    max_stale_min: float | None = None,
) -> tuple[dict | None, str]:
    """Short ATM straddle entered at ``entry``.

    The expiry is either given or the first one later than ``after``. Differences from the
    closed macro study: each leg is valued at the index of its own last trade (the closed
    study used the latest index for both), and a settlement fee is charged on the
    in-the-money leg.

    Returns
    -------
    (row, reason): row is None when the straddle cannot be built, and reason names why.
    """
    tr = load_window(ccy, entry)
    if tr.empty:
        return None, "empty window"
    tr = tr[tr["ts"] <= entry]
    if expiry is None:
        assert after is not None
        exps = np.sort(tr.loc[tr["expiry"] > after, "expiry"].unique())
        if not len(exps):
            return None, "no expiry after event"
        expiry = pd.Timestamp(exps[0])
    x = tr[tr["expiry"] == expiry].sort_values("ts")
    if x.empty:
        return None, "no trades on expiry"
    index = float(tr.sort_values("ts")["index_price"].iloc[-1])
    last = x.groupby(["strike", "right"]).tail(1).set_index(["strike", "right"])
    if max_stale_min is not None:
        age = (entry - last["ts"]).dt.total_seconds() / 60
        last = last[age <= max_stale_min]
    both = [
        k
        for k in last.index.get_level_values(0).unique()
        if (k, "C") in last.index and (k, "P") in last.index
    ]
    if not both:
        return None, "no strike with both legs"
    k = float(min(both, key=lambda s: abs(s - index)))
    sells = x[x["direction"] == "sell"]
    if len(sells) < CFG.min_sell_trades:
        return None, "too few taker sells"
    h = float(np.median((sells["mark_price"] - sells["price"]) / sells["mark_price"]))
    legs = [last.loc[(k, r)] for r in ("C", "P")]
    legs_mark = [float(lg["mark_price"]) * float(lg["index_price"]) for lg in legs]
    stale = max((entry - lg["ts"]).total_seconds() / 60 for lg in legs)
    legs_fill = [m * (1 - h) for m in legs_mark]
    fees = sum(min(CFG.taker_fee_underlying * index, CFG.fee_cap_share * f) for f in legs_fill)
    d_raw = deliv.get(expiry.date())
    if d_raw is None:
        return None, "no delivery price"
    d = float(d_raw)
    settle = abs(d - k)
    settle_fee = min(CFG.settle_fee_underlying * d, CFG.fee_cap_share * settle) if settle else 0.0
    premium = sum(legs_fill)
    pnl = premium - fees - settle - settle_fee
    return {
        "expiry": expiry,
        "strike": k,
        "index": index,
        "hours_to_expiry": (expiry - entry).total_seconds() / 3600,
        "stale_min": stale,
        "seller_discount": h,
        "premium_mark": sum(legs_mark),
        "premium": premium,
        "fees": fees + settle_fee,
        "settle": settle,
        "delivery": d,
        "ret_notional": pnl / index,
        "ret_premium": pnl / premium,
        "ret_mid_gross": (sum(legs_mark) - settle) / index,
        "implied_var": (sum(legs_mark) / (CFG.k_atm * index)) ** 2,
        "realised_var": float(np.log(d / index) ** 2),
        "abs_move": abs(float(np.log(d / index))),
        "n_trades_expiry": len(x),
    }, "ok"


def mean_ci(values: np.ndarray, dates: np.ndarray) -> tuple[float, float, float, int]:
    iv = date_clustered_ci(values, dates, stat=lambda v: float(np.mean(v)))
    return iv.point, iv.low, iv.high, iv.n
