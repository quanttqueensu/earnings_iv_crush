"""
wrds_r2.py
Read-only access to the QUANTT WRDS mirror on Cloudflare R2 (S3-compatible).

Data lives at ``s3://<bucket>/wrds/<schema>/<table>.parquet``. This module reads those
parquet tables directly with pyarrow (column projection + row-group predicate pushdown, so a
multi-GB table only transfers the columns and row groups asked for), and caches the projected
slice locally so repeat reads are offline. R2 egress is free; the cost is wall-time on the
first pull, so slices are cached under ``data/processed/wrds/raw/``.

Credentials are the ``R2_*`` names loaded from ``.env`` by :mod:`earnings_iv_crush.data.config`.
The token is scoped read-only. Nothing here writes to the bucket.

The mirror does not contain every schema the WRDS catalogue lists - notably the OptionMetrics
option schemas (``optionmsamp_us`` etc.) were never ingested. Reads of an absent schema/table
raise a clear error naming the gap rather than returning an empty frame.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence
from functools import lru_cache
from pathlib import Path
from typing import Any

import pandas as pd
import pyarrow.parquet as pq
from pyarrow.fs import FileSelector, FileType, S3FileSystem

from . import config

# ── cache location ───────────────────────────────────────────────────────────
_ROOT = Path(__file__).resolve().parents[2]
_CACHE_DIR = _ROOT / "data" / "processed" / "wrds" / "raw"

# Schemas known to be absent from the mirror, with the reason, so the error is actionable
# rather than a bare "not found".
_KNOWN_ABSENT = {
    "optionmsamp_us": "OptionMetrics US options were not ingested (separate licence/key needed)",
    "optionmsamp_europe": "OptionMetrics Europe was not ingested",
    "optionm_all": "full OptionMetrics was not ingested",
    "cboe_sample": "the CBOE per-contract option sample was not ingested",
}


class TableNotInMirror(RuntimeError):
    """Raised when a requested WRDS schema/table is absent from the R2 mirror."""


# ── filesystem ───────────────────────────────────────────────────────────────
@lru_cache(maxsize=1)
def _fs() -> S3FileSystem:
    """A cached S3 filesystem pointed at the R2 endpoint (read-only credentials)."""
    endpoint = config.R2_ENDPOINT_URL
    if not (endpoint and config.R2_ACCESS_KEY_ID and config.R2_SECRET_ACCESS_KEY):
        raise RuntimeError(
            "R2 credentials missing. Set R2_ENDPOINT_URL, R2_ACCESS_KEY_ID and "
            "R2_SECRET_ACCESS_KEY in .env (see .env for the WRDS mirror block)."
        )
    host = endpoint.replace("https://", "").replace("http://", "").rstrip("/")
    return S3FileSystem(
        access_key=config.R2_ACCESS_KEY_ID,
        secret_key=config.R2_SECRET_ACCESS_KEY,
        endpoint_override=host,
        scheme="https",
        region="auto",
    )


def _bucket() -> str:
    return config.R2_BUCKET


def _table_path(schema: str, table: str) -> str:
    """The object path ``<bucket>/wrds/<schema>/<table>.parquet``."""
    tbl = table if table.endswith(".parquet") else f"{table}.parquet"
    return f"{_bucket()}/wrds/{schema}/{tbl}"


# ── discovery ────────────────────────────────────────────────────────────────
@lru_cache(maxsize=1)
def list_schemas() -> tuple[str, ...]:
    """All schema directories present under ``wrds/`` in the bucket, sorted."""
    sel = FileSelector(f"{_bucket()}/wrds", recursive=False, allow_not_found=True)
    infos = _fs().get_file_info(sel)
    return tuple(sorted(i.path.split("/")[-1] for i in infos if i.type == FileType.Directory))


def list_tables(schema: str) -> list[str]:
    """Parquet table names (without extension) in a schema, sorted."""
    sel = FileSelector(f"{_bucket()}/wrds/{schema}", recursive=False, allow_not_found=True)
    infos = _fs().get_file_info(sel)
    return sorted(
        i.path.split("/")[-1].removesuffix(".parquet")
        for i in infos
        if i.type == FileType.File and i.path.endswith(".parquet")
    )


def table_exists(schema: str, table: str) -> bool:
    """True when ``<schema>/<table>.parquet`` is present in the mirror."""
    info = _fs().get_file_info(_table_path(schema, table))
    return info.type == FileType.File


def _assert_present(schema: str, table: str) -> None:
    if table_exists(schema, table):
        return
    if schema in _KNOWN_ABSENT:
        raise TableNotInMirror(
            f"{schema}/{table} is not in the R2 mirror: {_KNOWN_ABSENT[schema]}. "
            "Use the WRDS PostgreSQL path for that data."
        )
    schemas = list_schemas()
    if schema not in schemas:
        raise TableNotInMirror(
            f"schema '{schema}' is not in the mirror. Present schemas: {', '.join(schemas)}"
        )
    raise TableNotInMirror(
        f"table '{table}' not found in schema '{schema}'. Present tables: "
        f"{', '.join(list_tables(schema))}"
    )


# ── read ─────────────────────────────────────────────────────────────────────
def _cache_key(schema: str, table: str, columns: Any, filters: Any) -> Path:
    payload = json.dumps(
        {"schema": schema, "table": table, "columns": columns, "filters": repr(filters)},
        sort_keys=True,
    )
    digest = hashlib.sha1(payload.encode()).hexdigest()[:12]
    return _CACHE_DIR / f"{schema}.{table}.{digest}.parquet"


def read_table(
    schema: str,
    table: str,
    columns: Sequence[str] | None = None,
    filters: list[Any] | None = None,
    use_cache: bool = True,
) -> pd.DataFrame:
    """Read a WRDS table from the R2 mirror as a DataFrame.

    Parameters
    ----------
    schema, table : str
        Mirror location, e.g. ``("comp_na_daily_all", "fundq")``. ``.parquet`` optional.
    columns : sequence of str, optional
        Column projection. Only these column chunks are transferred; ``None`` reads all.
    filters : list, optional
        pyarrow predicate (DNF list of ``(col, op, value)`` tuples), pushed to the row-group
        level so non-matching row groups are skipped, e.g. ``[("rdq", ">=", "2015-01-01")]``.
    use_cache : bool
        When True (default) the projected slice is cached under
        ``data/processed/wrds/raw/`` and reused on the next identical call.

    Returns
    -------
    pandas.DataFrame

    Raises
    ------
    TableNotInMirror
        If the schema/table is absent from the mirror (names the gap).
    """
    cols = list(columns) if columns is not None else None
    cache = _cache_key(schema, table, cols, filters)
    if use_cache and cache.exists():
        return pd.read_parquet(cache)

    _assert_present(schema, table)
    tbl = pq.read_table(_table_path(schema, table), columns=cols, filters=filters, filesystem=_fs())
    df = tbl.to_pandas()

    if use_cache:
        _CACHE_DIR.mkdir(parents=True, exist_ok=True)
        df.to_parquet(cache, index=False)
    return df
