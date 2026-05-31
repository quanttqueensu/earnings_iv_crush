"""Assemble the clean per-event dataset the strategy trades on.

Joins earnings dates to ATM chains, computes front-week and back-month ATM IV,
the implied event move, and the trailing features the fair-move model needs.

The orchestration takes its providers by argument (defaulting to the
`data_intake` facade) so the whole build is testable against synthetic data and
swaps to live feeds with no code change. The per-event maths lives in
`features.py`.
"""
from __future__ import annotations

import pandas as pd
from pandas.tseries.offsets import BDay

from . import data_intake, features, surprise

# Output schema, in order. The first eight columns plus prior_surprise are
# computed now; eps_dispersion (WRDS/IBES) and oi_growth (historical OI
# snapshots) need sources that are not wired yet and stay NaN.
COLUMNS = [
    "ticker",
    "announce_date",
    "implied_move",
    "front_atm_iv",
    "back_atm_iv",
    "iv_term_spread",
    "trailing_rv",
    "skew_25d",
    "vol_premium",
    "variance_risk_premium",
    "bkm_skew",
    "bkm_kurt",
    "eps_dispersion",
    "prior_surprise",
    "oi_growth",
]
PENDING_FEATURES = ["eps_dispersion", "oi_growth"]


def _spot_from_prices(prices: pd.DataFrame) -> float:
    """Latest close as the spot reference, or NaN if no usable price."""
    if prices is None or prices.empty or "close" not in prices:
        return float("nan")
    close = pd.to_numeric(prices["close"], errors="coerce").dropna()
    return float(close.iloc[-1]) if not close.empty else float("nan")


def build_event_dataset(
    start: str,
    end: str,
    *,
    calendar: pd.DataFrame | None = None,
    fetch_chain=None,
    fetch_prices=None,
    asof_offset_days: int = 1,
    lookback_days: int = 60,
    rv_window: int = 20,
    r: float = 0.0,
) -> pd.DataFrame:
    """Return one row per earnings event with the fields the filters consume.

    Target columns:
        ticker, announce_date,
        implied_move, front_atm_iv, back_atm_iv, iv_term_spread,
        trailing_rv, skew_25d, eps_dispersion, prior_surprise, oi_growth

    Providers default to the `data_intake` facade but can be injected for
    testing. The chain/prices are pulled as of `asof_offset_days` business days
    before each announcement (the pre-event entry).
    """
    cal = calendar if calendar is not None else data_intake.fetch_earnings_calendar(start, end)
    fetch_chain = fetch_chain or data_intake.fetch_option_chain
    fetch_prices = fetch_prices or data_intake.fetch_equity_ohlcv

    if cal is None or len(cal) == 0:
        return pd.DataFrame(columns=COLUMNS)

    prior = surprise.prior_surprise(cal)   # aligned to cal.index; NaN if no EPS cols

    rows = []
    for idx, ev in cal.iterrows():
        ticker = ev["ticker"]
        announce = pd.Timestamp(pd.to_datetime(ev["announce_date"]))
        asof = announce - BDay(asof_offset_days)
        asof_str = asof.strftime("%Y-%m-%d")

        chain = fetch_chain(ticker, asof_str)
        prices = fetch_prices(
            ticker,
            (asof - pd.Timedelta(days=lookback_days)).strftime("%Y-%m-%d"),
            asof_str,
        )
        spot = _spot_from_prices(prices)

        feats = features.event_features(
            chain, spot, announce, asof, prices, r=r, rv_window=rv_window
        )
        row = {"ticker": ticker, "announce_date": announce, **feats}
        row["prior_surprise"] = float(prior.loc[idx]) if pd.notna(prior.loc[idx]) else float("nan")
        for col in PENDING_FEATURES:
            row[col] = float("nan")
        rows.append(row)

    return pd.DataFrame(rows, columns=COLUMNS)
