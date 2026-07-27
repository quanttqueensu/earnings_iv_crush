"""
config.py
Loads API keys from the project-root .env file.

Never hard-code keys and never commit .env. Code references key NAMES only;
the values live on disk in .env (git-ignored).

Uses python-dotenv when it is installed, and otherwise falls back to a small
built-in parser so the data layer imports cleanly with only the standard
library. Real process environment variables always take precedence over .env.
"""

from __future__ import annotations

import os
from pathlib import Path

# .env sits at the project root: this file is earnings_iv_crush/data/config.py, so go up two.
_ROOT = Path(__file__).resolve().parents[2]
_ENV_PATH = _ROOT / ".env"


def _parse_env_text(text: str) -> dict[str, str]:
    """Parse .env text into a dict. Ignores blanks and `#` comment lines.

    Strips one layer of matching single or double quotes around a value.
    """
    out: dict[str, str] = {}
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key, value = key.strip(), value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        if key:
            out[key] = value
    return out


def _load_dotenv(path: Path = _ENV_PATH) -> None:
    """Load .env into os.environ without overriding existing process vars."""
    try:
        from dotenv import load_dotenv  # type: ignore
    except ImportError:
        if not path.exists():
            return
        for key, value in _parse_env_text(path.read_text(encoding="utf-8")).items():
            os.environ.setdefault(key, value)
    else:
        load_dotenv(path)


_load_dotenv()

FRED_API_KEY = os.getenv("FRED_API_KEY", "")
TIINGO_API_KEY = os.getenv("TIINGO_API_KEY", "")
FINNHUB_API_KEY = os.getenv("FINNHUB_API_KEY", "")
ALPACA_KEY = os.getenv("ALPACA_KEY", "")
ALPACA_SECRET = os.getenv("ALPACA_SECRET", "")
SEC_USER_AGENT = os.getenv("SEC_USER_AGENT", "")

# QUANTT WRDS mirror on Cloudflare R2 (S3-compatible, read-only). The data layer
# reads parquet directly from the bucket; see data/wrds_r2.py.
R2_ENDPOINT_URL = os.getenv("R2_ENDPOINT_URL", "")
R2_ACCESS_KEY_ID = os.getenv("R2_ACCESS_KEY_ID", "")
R2_SECRET_ACCESS_KEY = os.getenv("R2_SECRET_ACCESS_KEY", "")
R2_BUCKET = os.getenv("R2_BUCKET", "quantt-historical-market-data")

# London Strategic Edge — free historical option chains with IV + Greeks.
LSE_API_KEY = os.getenv("LSE_API_KEY", "")


def require(name: str) -> str:
    """Return an env var, or raise a clear error telling the user to set it."""
    val = os.getenv(name, "")
    if not val:
        raise RuntimeError(
            f"Missing {name}. Copy .env.example to .env and add your key, " f"then re-run."
        )
    return val
