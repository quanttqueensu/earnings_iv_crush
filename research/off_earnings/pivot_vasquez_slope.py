"""
pivot_vasquez_slope.py
Candidate #6: the term-structure slope sort, with the earnings event removed.

This is the single experiment that separates two hypotheses the IV-crush project
cannot currently distinguish. Either the term signal carries nothing, or the
earnings event was the problem: announcement gap risk is what makes single-name
event variance roughly fairly priced, and Carr and Wu (2009) found single-name
variance risk premia insignificant for 32 of 35 stocks.

Vasquez ranks firms monthly on the slope of the implied volatility term structure,
defined as ``IV_LT - IV_1M`` where ``IV_1M`` is the average of the one-month ATM
call and put implied volatilities. On OptionMetrics from 1996 he reports the
lowest-slope decile returning -9.2% per month on straddles, the highest +7.3%, and
a long-short of +16.5% per month at t = 10.02.

The IV-crush gate sold straddles on names whose front-week IV sat far above the
back month. That is a **negative** slope in this convention, which is Vasquez's
short leg. The direction was right. What the book added was the event.

Execution, which is the whole question
--------------------------------------
Vasquez holds options to maturity "to avoid paying high transaction costs more
than once". Saretto reports an average volume-weighted quoted spread of 8.0% on
near-ATM options and argues profitability survives because "the effective spread
is generally lower than the quoted one". The fills study on this project measured
34,672 prints and found median price improvement of **zero**, with 54% paying the
full touch. That contradiction is the contribution here, so both a mid-priced and
a full-touch arm are scored and reported side by side.

Sample note: the free DoltHub panel covers roughly 2019 to late 2024 and therefore
does **not** overlap Vasquez's sample. This is an out-of-sample test on a later
regime, not a replication.

Cost and runtime
----------------
Zero metered spend: DoltHub is a free keyless public database. The cost is
wall-clock, one HTTP call per ticker-month. The build is checkpointed and
resumable, and ``--max-calls`` bounds any single session.

Run:
    python research/off_earnings/pivot_vasquez_slope.py --build --max-calls 2000
    python research/off_earnings/pivot_vasquez_slope.py --score
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from earnings_iv_crush.data import dolthub_options as dolt  # noqa: E402
from earnings_iv_crush.engine.alpha_adjudication import TrialLedger  # noqa: E402
from earnings_iv_crush.engine.screen import gross_gate, score_signal  # noqa: E402

OUT_DIR = Path("outputs/research/pivot")
PANEL_PATH = OUT_DIR / "vasquez_panel.parquet"
LEDGER = OUT_DIR / "trial_ledger.json"

START, END = "2019-01-01", "2024-10-31"

# Verified against the DoltHub API: option_chain carries exactly three expiries per
# snapshot, consistently near 14, 28 and 49 days (checked on AAPL 2021-03-31 and
# 2023-06-30, MSFT 2023-06-30, XOM 2022-09-30). There is no long-dated leg, so
# Vasquez's IV_LT cannot be built here. What follows is a SHORT-DATED slope, front
# expiry against the third expiry, and must never be reported as a Vasquez
# replication. It remains the right test of the question that matters: whether the
# term signal works once the earnings event is removed.
SHORT_DTE = (7, 21)  # front expiry
LONG_DTE = (35, 60)  # third expiry
N_BUCKETS = 5  # quintiles, not deciles: the free panel cannot support 10 cells


def month_ends(start: str, end: str) -> list[str]:
    """Month-end calendar dates, as ISO strings."""
    return [d.strftime("%Y-%m-%d") for d in pd.date_range(start, end, freq="ME")]


def implied_spot(chain: pd.DataFrame) -> float:
    """Recover the underlying from the chain via put-call parity.

    The DoltHub adapter returns no spot column, and joining CRSP for it would add a
    second data dependency to every row. Parity gives it for free: ``C - P = S -
    K e^{-rT}``, so the strike at which the call and put mids are closest is the
    strike nearest the forward, and at short maturities with rates near zero that
    is a good proxy for spot.

    Returns
    -------
    float
        Estimated spot, or NaN when no strike has both sides quoted.
    """
    mid = (
        pd.to_numeric(chain["bid"], errors="coerce") + pd.to_numeric(chain["ask"], errors="coerce")
    ) / 2.0
    work = chain.assign(mid=mid).dropna(subset=["mid"])
    if work.empty:
        return float("nan")
    front = work[work["dte"] == work["dte"].min()]
    pivot = front.pivot_table(index="strike", columns="right", values="mid", aggfunc="mean")
    if not {"C", "P"}.issubset(pivot.columns):
        return float("nan")
    pivot = pivot.dropna(subset=["C", "P"])
    if pivot.empty:
        return float("nan")
    return float((pivot["C"] - pivot["P"]).abs().idxmin())


def _atm_iv(chain: pd.DataFrame, spot: float, window: tuple[int, int]) -> float:
    """Average ATM call and put IV for contracts with DTE in ``[lo, hi)``.

    Averaging the two sides follows Vasquez's ``IV_1M`` definition and cancels
    most of the put-call skew, so the slope measures term structure rather than
    which side of the smile the nearest strike happened to land on.
    """
    lo, hi = window
    if chain.empty or not np.isfinite(spot) or spot <= 0:
        return float("nan")
    sub = chain[(chain["dte"] >= lo) & (chain["dte"] < hi)]
    if sub.empty:
        return float("nan")
    # Nearest-to-money strike within the bucket, then average the two rights.
    sub = sub.assign(moneyness=(sub["strike"] / spot - 1.0).abs())
    nearest = sub.nsmallest(6, "moneyness")
    ivs = pd.to_numeric(nearest["iv"], errors="coerce").dropna()
    return float(ivs.mean()) if len(ivs) else float("nan")


def build(tickers: list[str], max_calls: int) -> None:
    """Extend the month-end slope panel, resuming from whatever exists."""
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    done: set[tuple[str, str]] = set()
    rows: list[dict] = []
    if PANEL_PATH.exists():
        existing = pd.read_parquet(PANEL_PATH)
        rows = existing.to_dict("records")
        done = {(str(r["ticker"]), str(r["asof"])) for r in rows}
        print(f"resuming: {len(done):,} ticker-months already built")

    targets = [(t, d) for d in month_ends(START, END) for t in tickers if (t, d) not in done]
    print(f"{len(targets):,} ticker-months outstanding; this session caps at {max_calls:,}")

    calls = 0
    started = time.time()
    for ticker, asof in targets:
        if calls >= max_calls:
            break
        calls += 1
        try:
            chain = dolt.fetch_option_chain(ticker, asof, horizon_days=180)
        except Exception as exc:  # network/vendor errors must not kill a long build
            rows.append({"ticker": ticker, "asof": asof, "error": str(exc)[:120]})
            continue
        if chain.empty:
            rows.append({"ticker": ticker, "asof": asof, "error": "empty chain"})
            continue

        chain = chain.copy()
        chain["dte"] = (pd.to_datetime(chain["expiry"]) - pd.Timestamp(asof)).dt.days
        spot = implied_spot(chain)
        iv_short = _atm_iv(chain, spot, SHORT_DTE)
        iv_long = _atm_iv(chain, spot, LONG_DTE)
        rows.append(
            {
                "ticker": ticker,
                "asof": asof,
                "iv_front": iv_short,
                "iv_back": iv_long,
                # Signed as Vasquez signs it: back minus front, so a steep front
                # (the IV-crush gate's trigger) is a negative slope.
                "slope": iv_long - iv_short,
                "spot": spot,
                "error": None,
            }
        )
        if calls % 100 == 0:
            rate = calls / max(time.time() - started, 1e-9)
            print(f"  {calls:,}/{max_calls:,} calls  ({rate:.1f}/s)")
            pd.DataFrame(rows).to_parquet(PANEL_PATH, index=False)

    pd.DataFrame(rows).to_parquet(PANEL_PATH, index=False)
    built = sum(1 for r in rows if r.get("error") is None)
    print(f"\npanel: {built:,} usable ticker-months of {len(rows):,} attempted")
    print(f"written: {PANEL_PATH.resolve()}")


def score() -> int:
    """Sort on slope, score forward straddle-proxy returns, report both cost arms."""
    if not PANEL_PATH.exists():
        print(f"No panel at {PANEL_PATH}. Run with --build first.")
        return 1

    panel = pd.read_parquet(PANEL_PATH)
    panel = panel[panel["error"].isna()].dropna(subset=["slope", "spot"])
    panel["asof"] = pd.to_datetime(panel["asof"])
    print(f"panel: {len(panel):,} usable ticker-months, {panel['ticker'].nunique()} names")

    # Forward one-month straddle proxy: a delta-neutral straddle's return is driven by
    # realised minus implied variance over the holding month. Using the underlying's
    # own realised move against the entry implied move keeps this free of a second
    # chain pull, at the cost of ignoring the gamma path.
    panel = panel.sort_values(["ticker", "asof"])
    panel["spot_next"] = panel.groupby("ticker")["spot"].shift(-1)
    panel["realised_move"] = (panel["spot_next"] / panel["spot"] - 1.0).abs()
    panel["implied_move"] = panel["iv_front"] / np.sqrt(12.0)
    panel = panel.dropna(subset=["realised_move", "implied_move"])

    # Short-straddle return proxy, gross: implied move collected less realised move paid.
    panel["straddle_gross"] = panel["implied_move"] - panel["realised_move"]

    ledger = TrialLedger(LEDGER)
    ledger.declare_grid(
        "vasquez_slope", {"bucket": list(range(N_BUCKETS)), "arm": ["mid", "touch"]}
    )

    panel["bucket"] = panel.groupby("asof")["slope"].transform(
        lambda s: (
            pd.qcut(s.rank(method="first"), N_BUCKETS, labels=False)
            if s.notna().sum() >= N_BUCKETS
            else np.nan
        )
    )
    panel = panel.dropna(subset=["bucket"])

    results = []
    for arm, cost in (("mid", 0.0), ("touch", 0.080)):
        # 8.0% quoted round-trip on premium (Saretto), charged in full on the touch arm
        # because the fills study found median price improvement of zero.
        for bucket in range(N_BUCKETS):
            sub = panel[panel["bucket"] == bucket]
            if len(sub) < 30:
                print(f"  {arm} bucket {bucket}: N={len(sub)}, too thin to score")
                continue
            ret = sub["straddle_gross"] - cost * sub["implied_move"]
            gate = gross_gate(ret, f"vasquez::{arm}::b{bucket}", require_positive_mean=False)
            print("  " + gate.report().replace("\n", "\n  "))
            res = score_signal(
                ret,
                sub["asof"],
                f"vasquez_slope::arm={arm}_bucket={bucket}",
                cadence="calendar",
                cluster_keys=sub["asof"],
                n_trials=ledger.n_trials,
                gross=(arm == "mid"),
            )
            ledger.record(f"vasquez_slope::arm={arm}_bucket={bucket}", {"sharpe": res.sharpe})
            results.append(res)
            print("    " + res.summary())

    if results:
        table = pd.DataFrame([r.to_row() for r in results])
        out = OUT_DIR / "vasquez_slope.csv"
        table.to_csv(out, index=False)
        print(f"\nwritten: {out.resolve()}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--build", action="store_true", help="extend the month-end panel")
    ap.add_argument("--score", action="store_true", help="score the existing panel")
    ap.add_argument("--max-calls", type=int, default=2000, help="cap HTTP calls this session")
    ap.add_argument("--universe", type=str, default="", help="comma-separated tickers")
    args = ap.parse_args()

    tickers = (
        [t.strip().upper() for t in args.universe.split(",") if t.strip()]
        if args.universe
        else DEFAULT_UNIVERSE
    )

    if args.build:
        build(tickers, args.max_calls)
    if args.score:
        return score()
    if not args.build:
        ap.print_help()
    return 0


#: Liquid optionable large caps spanning sectors. Kept modest because the panel costs
#: one HTTP call per ticker-month and quintiles need only ~5 names per cell.
DEFAULT_UNIVERSE = [
    "AAPL",
    "MSFT",
    "AMZN",
    "GOOGL",
    "META",
    "NVDA",
    "TSLA",
    "JPM",
    "BAC",
    "WFC",
    "XOM",
    "CVX",
    "COP",
    "JNJ",
    "PFE",
    "MRK",
    "UNH",
    "ABBV",
    "LLY",
    "TMO",
    "PG",
    "KO",
    "PEP",
    "WMT",
    "COST",
    "HD",
    "MCD",
    "NKE",
    "SBUX",
    "TGT",
    "V",
    "MA",
    "AXP",
    "GS",
    "MS",
    "C",
    "SCHW",
    "BLK",
    "SPGI",
    "CME",
    "INTC",
    "AMD",
    "QCOM",
    "TXN",
    "AVGO",
    "CRM",
    "ORCL",
    "ADBE",
    "CSCO",
    "IBM",
    "BA",
    "CAT",
    "DE",
    "HON",
    "GE",
    "LMT",
    "RTX",
    "UPS",
    "FDX",
    "UNP",
    "T",
    "VZ",
    "CMCSA",
    "DIS",
    "NFLX",
    "SO",
    "DUK",
    "NEE",
    "AMT",
    "PLD",
]


if __name__ == "__main__":
    raise SystemExit(main())
