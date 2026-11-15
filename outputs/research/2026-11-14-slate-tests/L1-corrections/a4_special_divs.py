"""
a4_special_divs.py
A4: dividends inside hedged holds that OCC may have adjusted by strike (a non-ordinary cash
dividend of at least USD 12.50 per contract), and what settling on the adjusted strike would do.

Usage
-----
    python outputs/research/2026-11-14-slate-tests/L1-corrections/a4_special_divs.py

OCC's rule (By-Laws Article VI, Section 11A, recalled and not verified at source): a cash
dividend that is not declared under a regular dividend policy, of USD 12.50 or more per
contract, is adjusted by reducing the strike by the dividend per share; an ordinary dividend is
never adjusted, whatever its size. The hold settles at ``|S - K|`` on the unadjusted strike.
For an adjusted contract the settlement is ``|S - (K - D)|``. This script lists every flagged
event of ``base_corrected.parquet``, every in-hold dividend of at least USD 0.125 per share
(USD 12.50 per contract) with its classifier label, and the settlement change on each flagged
event under the assumption that OCC adjusted it (an upper bound, since only a non-ordinary
declaration is adjusted). The hedge after the ex-date still uses the unadjusted strike; that
second-order term is not re-valued. Writes ``a4_results.json`` and ``a4_events.csv``
(aggregates and event keys only: tickers, dates, strikes and the project's own figures).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from earnings_iv_crush.config import HOLD_CORRECTIONS as FC  # noqa: E402

HERE = Path(__file__).resolve().parent
BASE = HERE / "base_corrected.parquet"
CRSP = ROOT / "outputs" / "research" / "2026-10-20-hedged-hold" / "crsp_paths.parquet"


def _crsp() -> dict[int, pd.DataFrame]:
    c = pd.read_parquet(CRSP, columns=["permno", "date", "prc", "ret", "cfacpr"])
    c["date"] = pd.to_datetime(c["date"])
    for col in ("prc", "ret", "cfacpr"):
        c[col] = pd.to_numeric(c[col], errors="coerce").astype(float)
    c["prc"] = c["prc"].abs()
    return {int(k): g.set_index("date").sort_index() for k, g in c.groupby("permno")}


def _divs(g: pd.DataFrame, lo: pd.Timestamp, hi: pd.Timestamp) -> list[tuple]:
    """(ex_date, D, cum close) from CRSP total against price return, as ``build_base`` does."""
    w = g.loc[(g.index >= lo - pd.Timedelta(days=10)) & (g.index <= hi)]
    out = []
    for d, p, pp, r, cf, cfp in zip(
        w.index,
        w["prc"],
        w["prc"].shift(1),
        w["ret"],
        w["cfacpr"],
        w["cfacpr"].shift(1),
        strict=True,
    ):
        if d <= lo or not (np.isfinite(pp) and np.isfinite(r)) or cf != cfp:
            continue
        div = (1 + r) * pp - p
        if div > FC.min_recovered_div:
            out.append((pd.Timestamp(d), float(div), float(pp)))
    return out


def main() -> None:
    b = pd.read_parquet(BASE)
    for c in ("entry_date", "exit_date", "expiry"):
        b[c] = pd.to_datetime(b[c])
    crsp = _crsp()
    big = b[b["div_in_hold"] >= FC.special_div_per_contract / FC.contract_multiplier]
    print(f"events with in-hold dividends >= USD 0.125/share: {len(big)} of {len(b)}")
    print(big.groupby(["block", "special_div"], dropna=False).size().to_string())
    rows = []
    for _, e in b[b["special_div"].eq(True)].iterrows():
        g = crsp.get(int(e["permno"]))
        if g is None:
            raise RuntimeError(f"no CRSP path for flagged event {e['ticker']} {e['entry_date']}")
        dv = _divs(g, e["entry_date"], e["expiry"])
        settle_day = g.index[g.index <= e["expiry"]].max()
        s = float(g.loc[settle_day, "prc"])
        k = float(e["strike"])
        d_tot = float(sum(x[1] for x in dv))
        old, new = abs(s - k), abs(s - (k - d_tot))
        rows.append(
            {
                "ticker": e["ticker"],
                "entry_date": e["entry_date"].date(),
                "expiry": e["expiry"].date(),
                "block": e["block"],
                "ex_dates": ";".join(str(x[0].date()) for x in dv),
                "div_per_share": round(d_tot, 4),
                "div_per_contract": round(d_tot * FC.contract_multiplier, 2),
                "div_over_cum_close": round(max(x[1] / x[2] for x in dv), 4),
                "strike": k,
                "adjusted_strike_if_occ": round(k - d_tot, 4),
                "settle_minus_strike": round(s - k, 4),
                "settlement_change_pct_m0": round(100 * (old - new) / e["m0"], 4),
                "H_corr_pct_m0": round(100 * e["H_corr"], 4),
                "call_assigned_early": bool(e["call_assigned"]),
            }
        )
    ev = pd.DataFrame(rows)
    ev.to_csv(HERE / "a4_events.csv", index=False)
    res: dict = {
        "n_flagged": int(len(ev)),
        "n_div_ge_0125_by_block_and_flag": {
            f"{k[0]}|{k[1]}": int(v)
            for k, v in big.groupby(["block", "special_div"], dropna=False).size().items()
        },
        "events": ev.to_dict("records"),
    }
    for blk, n in b.groupby("block").size().items():
        x = ev.loc[ev["block"] == blk, "settlement_change_pct_m0"]
        res[f"block_mean_change_upper_bound_{blk}"] = {
            "pct_m0_per_trade": float(x.sum() / n),
            "n_block": int(n),
            "n_flagged": int(len(x)),
        }
    (HERE / "a4_results.json").write_text(json.dumps(res, indent=1, default=str), encoding="utf-8")
    print(ev.to_string())
    print(json.dumps({k: v for k, v in res.items() if k != "events"}, indent=1))


if __name__ == "__main__":
    main()
