"""cache.py
Local on-disk cache for collected market-data frames.

Surface panels and joined event datasets are expensive to assemble from the
providers, so they are cached under the git-ignored ``data/`` tree. Parquet is
used when an engine is available and CSV is the dependency-free fallback, so the
cache works whether or not ``pyarrow`` is installed.

This module implements:

* ``cache_path``    — resolve the on-disk path for a cache key.
* ``write_frame``   — persist a DataFrame (parquet, or CSV fallback).
* ``read_frame``    — load a cached DataFrame by key.
* ``has_frame``     — check whether a key is cached.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

DEFAULT_CACHE_DIR = Path("data") / "processed"


def cache_path(key: str, cache_dir: str | Path = DEFAULT_CACHE_DIR) -> Path:
    """Parquet path for ``key`` under ``cache_dir`` (no existence guarantee)."""
    return Path(cache_dir) / f"{key}.parquet"


def write_frame(df: pd.DataFrame, key: str, cache_dir: str | Path = DEFAULT_CACHE_DIR) -> Path:
    """
    Persist ``df`` under ``key``; return the written path.

    Writes parquet when a parquet engine is installed, otherwise falls back to a
    sibling ``.csv``. The parent directory is created if needed.
    """
    path = cache_path(key, cache_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        df.to_parquet(path)
        return path
    except (ImportError, ValueError):
        csv_path = path.with_suffix(".csv")
        df.to_csv(csv_path, index=False)
        return csv_path


def read_frame(key: str, cache_dir: str | Path = DEFAULT_CACHE_DIR) -> pd.DataFrame:
    """
    Load the cached frame for ``key`` (parquet preferred, then CSV).

    Raises
    ------
    FileNotFoundError
        If neither a parquet nor a CSV file exists for ``key``.
    """
    parquet = cache_path(key, cache_dir)
    csv = parquet.with_suffix(".csv")
    if parquet.exists():
        return pd.read_parquet(parquet)
    if csv.exists():
        return pd.read_csv(csv)
    raise FileNotFoundError(f"no cached frame for key {key!r} under {cache_dir}")


def has_frame(key: str, cache_dir: str | Path = DEFAULT_CACHE_DIR) -> bool:
    """True when a parquet or CSV cache file exists for ``key``."""
    parquet = cache_path(key, cache_dir)
    return parquet.exists() or parquet.with_suffix(".csv").exists()
