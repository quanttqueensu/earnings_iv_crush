"""
reverse_alpha_quotes.py
Attach the real two-sided quotes for the contract each event actually trades.

``market_validate.market_marks`` returns the straddle mid at entry and exit and, as an
audit field, the exit ask. That is enough to price a modelled cost stack and not enough to
price the trade. A short straddle is opened by selling into the bid and closed by buying
the ask, so the executable round trip is ``entry_bid - exit_ask`` and every other pairing
flatters it.

This makes a second pass over the same cached chains, keyed on the strike and expiry the
marking pass already chose, and records all four quotes on both legs. Nothing is modelled:
where a side is missing the row carries NaN and the execution analysis reports the coverage
rather than substituting a mid.

The quoted width is also the input Phase 9 needs to answer the question that decides
whether any of this is tradable, namely whether the events a signal selects are more
expensive to trade than the unconditional book. An unconditional average cost applied to a
selected population assumes the answer.

Usage:
    python research/selection/reverse_alpha_quotes.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from earnings_iv_crush.data import databento_quotes as dq  # noqa: E402
from research.selection.reverse_alpha_panel import BLOCKS, OUT, marked_events  # noqa: E402

CACHE = OUT / "quotes.parquet"


def _leg(chain: pd.DataFrame, expiry, strike: float, right: str) -> tuple[float, float]:
    """Bid and ask for one leg, or NaN when the contract is not quoted two-sided."""
    s = chain[
        (chain["expiry"] == expiry)
        & (np.isclose(chain["strike"], strike))
        & (chain["right"] == right)
    ]
    if s.empty:
        return float("nan"), float("nan")
    row = s.iloc[0]
    bid = pd.to_numeric(pd.Series([row.get("bid", np.nan)]), errors="coerce").iloc[0]
    ask = pd.to_numeric(pd.Series([row.get("ask", np.nan)]), errors="coerce").iloc[0]
    return float(bid), float(ask)


def straddle_quotes(chain: pd.DataFrame, expiry, strike: float) -> dict[str, float]:
    """Both legs' quotes summed into a straddle bid and ask."""
    cb, ca = _leg(chain, expiry, strike, "C")
    pb, pa = _leg(chain, expiry, strike, "P")
    return {
        "bid": cb + pb,
        "ask": ca + pa,
        "call_bid": cb,
        "call_ask": ca,
        "put_bid": pb,
        "put_ask": pa,
    }


def block_quotes(label: str, path: str) -> pd.DataFrame:
    """One row per event carrying the entry and exit two-sided straddle quotes."""
    ev = marked_events(label, path)
    rows: list[dict] = []
    for _, e in ev.iterrows():
        k, exp = e.get("strike_mkt", np.nan), e.get("expiry_mkt", None)
        rec: dict[str, object] = {
            "ticker": e["ticker"],
            "entry_date": e["entry_date"],
            "block": label,
        }
        if np.isfinite(pd.to_numeric(k, errors="coerce")) and exp is not None:
            for when, col in (("entry", "entry_date"), ("exit", "exit_date")):
                p = dq.cache_path(e["ticker"], pd.Timestamp(e[col]))
                if not p.exists():
                    continue
                ch = pd.read_parquet(p)
                if ch.empty:
                    continue
                q = straddle_quotes(ch, exp, float(k))
                rec.update({f"{when}_{key}": val for key, val in q.items()})
        rows.append(rec)
    out = pd.DataFrame(rows)
    have = out.get("entry_bid", pd.Series(dtype=float)).notna().sum()
    print(f"  {label}: {have} of {len(out)} events carry a two-sided entry quote")
    return out


def load_quotes(rebuild: bool = False) -> pd.DataFrame:
    """The cached two-sided quote table, built on first use."""
    if CACHE.exists() and not rebuild:
        return pd.read_parquet(CACHE)
    OUT.mkdir(parents=True, exist_ok=True)
    print("reading cached chains for real two-sided quotes ...")
    q = pd.concat([block_quotes(k, v) for k, v in BLOCKS.items()], ignore_index=True)
    q.to_parquet(CACHE, index=False)
    print(f"wrote {CACHE.resolve()}")
    return q


def main() -> None:
    q = load_quotes()
    for blk, g in q.groupby("block"):
        eb, ea = g.get("entry_bid"), g.get("entry_ask")
        xb, xa = g.get("exit_bid"), g.get("exit_ask")
        emid, xmid = (ea + eb) / 2, (xa + xb) / 2
        ew = np.where(emid > 0, (ea - eb) / emid, np.nan)
        xw = np.where(xmid > 0, (xa - xb) / xmid, np.nan)
        print(
            f"\n{blk}: quoted full width as a fraction of mid\n"
            f"  entry  median {np.nanmedian(ew):.4f}  mean {np.nanmean(ew):.4f}  "
            f"n={int(np.isfinite(ew).sum())}\n"
            f"  exit   median {np.nanmedian(xw):.4f}  mean {np.nanmean(xw):.4f}  "
            f"n={int(np.isfinite(xw).sum())}"
        )


if __name__ == "__main__":
    main()
