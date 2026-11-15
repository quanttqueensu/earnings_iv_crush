"""fexlib.py: shared loaders for the ForecastEx pilot (pairs, prices, Kalshi twins)."""
from __future__ import annotations

from pathlib import Path

import pandas as pd

DATA = Path(__file__).resolve().parents[1] / "data"


def parse_ts(s: pd.Series) -> pd.Series:
    """ForecastEx timestamps carry up to nine fractional digits; keep six and parse as UTC."""
    return pd.to_datetime(s.str.replace(r"(\.\d{1,6})\d*", r"\1", regex=True), utc=True,
                          format="ISO8601")


def load_pairs() -> pd.DataFrame:
    p = pd.read_parquet(DATA / "pairs_econ.parquet")
    p["t"] = parse_ts(p.pair_time)
    p["exp"] = parse_ts(p.expiration_date)
    p["y"] = p.yes_price.astype(float)
    p["q"] = p.quantity.astype(float)
    p["h"] = (p.exp - p.t).dt.total_seconds() / 3600
    return p
