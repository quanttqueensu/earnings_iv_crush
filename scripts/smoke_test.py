"""
smoke_test.py
Pull one small sample from each wired data source.

No-key sources (FRED VIX, yfinance, SEC EDGAR) run immediately - SEC only
needs SEC_USER_AGENT in .env. Keyed sources (Finnhub) print SKIP until you add
the key. A source that errors prints FAIL with the reason but does not stop the
others.

Usage
-----
From the project root::

    python scripts/smoke_test.py
"""
from __future__ import annotations

import sys
from pathlib import Path

# Make `import src...` work when run from the project root.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.data import vix, equities, sec_edgar, earnings          # noqa: E402
from src.data.config import FINNHUB_API_KEY, SEC_USER_AGENT       # noqa: E402


def section(name: str) -> None:
    print("\n" + "=" * 64 + f"\n  {name}\n" + "=" * 64)


def show(df) -> None:
    if df is None or len(df) == 0:
        print("  (no rows returned)")
    else:
        print(df.tail(3).to_string(index=False))


def main() -> None:
    section("1. FRED VIX  (no key)")
    try:
        show(vix.fetch_index_vol("2026-05-01", "2026-05-29"))
    except Exception as exc:
        print("  FAIL:", exc)

    section("2. yfinance equities  (no key)")
    try:
        show(equities.fetch_equity_ohlcv("AAPL", "2026-05-01", "2026-05-29"))
    except Exception as exc:
        print("  FAIL:", exc)

    section("3. SEC EDGAR earnings 8-Ks  (no key, needs SEC_USER_AGENT)")
    if not SEC_USER_AGENT:
        print("  SKIP: set SEC_USER_AGENT in .env")
    else:
        try:
            show(sec_edgar.earnings_8ks("AAPL"))
        except Exception as exc:
            print("  FAIL:", exc)

    section("4. Finnhub earnings calendar  (needs FINNHUB_API_KEY)")
    if not FINNHUB_API_KEY:
        print("  SKIP: set FINNHUB_API_KEY in .env")
    else:
        try:
            show(earnings.fetch_earnings_calendar("2026-06-01", "2026-06-05"))
        except Exception as exc:
            print("  FAIL:", exc)

    print("\nDone. No-key sources should show rows; keyed sources show SKIP "
          "until you add their keys to .env.\n")


if __name__ == "__main__":
    main()
