"""
data_pipeline.py
Assemble the clean per-event dataset the strategy trades on.

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

# Output schema, in order. eps_dispersion comes from the free-first dispersion
# stack (per-ticker snapshot proxy until WRDS lands); oi_growth is the
# snapshot OI proxy and only populates when use_oi_proxy=True because it is
# not point-in-time.
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
PENDING_FEATURES: list[str] = []


def _spot_from_prices(prices: pd.DataFrame) -> float:
    """Latest close as the spot reference, or NaN if no usable price."""
    if prices is None or prices.empty or "close" not in prices:
        return float("nan")
    close = pd.to_numeric(prices["close"], errors="coerce").dropna()
    return float(close.iloc[-1]) if not close.empty else float("nan")


# ── Dataset build ────────────────────────────────────────────────────────────


def build_event_dataset(
    start: str,
    end: str,
    *,
    calendar: pd.DataFrame | None = None,
    fetch_chain=None,
    fetch_prices=None,
    fetch_dispersion=None,
    use_oi_proxy: bool = False,
    asof_offset_days: int = 1,
    lookback_days: int = 60,
    rv_window: int = 20,
    r: float = 0.0,
) -> pd.DataFrame:
    """Return one row per earnings event with the fields the filters consume.

    The output frame carries ``COLUMNS`` in order: ``ticker``, ``announce_date``,
    ``implied_move``, ``front_atm_iv``, ``back_atm_iv``, ``iv_term_spread``,
    ``trailing_rv``, ``skew_25d``, ``vol_premium``, ``variance_risk_premium``,
    ``bkm_skew``, ``bkm_kurt``, ``eps_dispersion``, ``prior_surprise`` and
    ``oi_growth``. The chain and prices are pulled as of ``asof_offset_days``
    business days before each announcement (the pre-event entry).

    Parameters
    ----------
    start, end : str
        Backtest window bounds (``YYYY-MM-DD``); used only to fetch the calendar
        when ``calendar`` is not supplied.
    calendar : pd.DataFrame, optional
        Earnings calendar with ``ticker`` and ``announce_date``. Defaults to the
        ``data_intake`` facade's calendar for the window.
    fetch_chain : callable, optional
        ``fetch_chain(ticker, 'YYYY-MM-DD') -> chain``. Defaults to
        ``data_intake.fetch_option_chain``; injectable for testing.
    fetch_prices : callable, optional
        ``fetch_prices(ticker, start, end) -> OHLCV``. Defaults to
        ``data_intake.fetch_equity_ohlcv``; injectable for testing.
    fetch_dispersion : callable, optional
        ``fetch_dispersion(ticker, start, end) -> frame`` with ``eps_mean``
        and ``eps_std``. Defaults to ``data_intake.fetch_analyst_dispersion``;
        injectable for testing. Fetched once per ticker; on the free stack the
        value is a per-ticker snapshot proxy, not point-in-time.
    use_oi_proxy : bool, optional
        Populate ``oi_growth`` with the snapshot open-interest proxy. The
        proxy is not point-in-time, so it defaults to ``False`` and should
        only be enabled for robustness work.
    asof_offset_days : int, optional
        Business days before the announcement at which to read the entry chain
        and prices. Defaults to ``1``.
    lookback_days : int, optional
        Calendar days of price history to pull before the as-of date for the
        realised-vol window. Defaults to ``60``.
    rv_window : int, optional
        Trailing-return window for realised vol, in observations. Defaults to
        ``20``.
    r : float, optional
        Risk-free rate passed to the feature maths. Defaults to ``0.0``.

    Returns
    -------
    pd.DataFrame
        One row per calendar event with ``COLUMNS``; empty (correctly typed)
        when the calendar is empty. ``eps_dispersion`` and ``oi_growth`` stay
        NaN until their sources are wired (see ``PENDING_FEATURES``).
    """
    cal = calendar if calendar is not None else data_intake.fetch_earnings_calendar(start, end)
    fetch_chain = fetch_chain or data_intake.fetch_option_chain
    fetch_prices = fetch_prices or data_intake.fetch_equity_ohlcv
    fetch_dispersion = fetch_dispersion or data_intake.fetch_analyst_dispersion

    if cal is None or len(cal) == 0:
        return pd.DataFrame(columns=COLUMNS)

    prior = surprise.prior_surprise(cal)  # aligned to cal.index; NaN if no EPS cols

    # One dispersion value per ticker: normalised estimate std (eps_std / |eps_mean|).
    dispersion: dict[str, float] = {}
    for ticker in pd.unique(cal["ticker"]):
        try:
            disp = fetch_dispersion(ticker, start, end)
        except Exception:
            disp = None
        value = float("nan")
        if disp is not None and len(disp) > 0:
            row0 = disp.iloc[-1]
            mean, std = row0.get("eps_mean"), row0.get("eps_std")
            if pd.notna(mean) and pd.notna(std) and abs(float(mean)) > 0:
                value = float(std) / abs(float(mean))
        dispersion[ticker] = value

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
        row["eps_dispersion"] = dispersion.get(ticker, float("nan"))
        row["oi_growth"] = (
            features.oi_snapshot_proxy(chain, prices) if use_oi_proxy else float("nan")
        )
        rows.append(row)

    return pd.DataFrame(rows, columns=COLUMNS)
