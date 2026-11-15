"""c1_borrow_build.py: option-implied borrow at the entry 15:59 chain, two expiries, spot-free.

For each event of the corrected panel, the entry 15:59 parent chain gives a parity forward on the
front (event) expiry and on a back expiry; the borrow implied by their ratio is

    b = r - ln(F2 / (F1 - D_gap)) / (T2 - T1),

with r the federal funds rate on the entry date (ACT/360 converted to ACT/365) and D_gap the
regular dividends projected causally into (T1, T2]. Writes ``c1_borrow.parquet`` and prints the
funnel. No outcome is read.

Usage
-----
    python outputs/research/2026-11-14-slate-tests/L3-selection/c1_borrow_build.py

References
----------
Ofek, E., Richardson, M. and Whitelaw, R. (2004). Limited arbitrage and short sales restrictions:
evidence from the options markets. Journal of Financial Economics 74, 305-342.
"""

from __future__ import annotations

import sys
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from lib import BASE, ROOT  # noqa: E402

CHAINS = ROOT / "data" / "cache" / "backfill_chains"
CRSP = ROOT / "outputs" / "research" / "2026-10-20-hedged-hold" / "crsp_paths.parquet"
YDIV = ROOT / "outputs" / "research" / "parity_spread" / "dividends.parquet"
DFF = (
    ROOT / "outputs" / "research" / "2026-11-13-alpha-hunt" / "lane1-macro" / "dl" / "fred_DFF.csv"
)
OUT = HERE / "c1_borrow.parquet"


@dataclass(frozen=True)
class BorrowConfig:
    """Constants of the implied-borrow build.

    Attributes
    ----------
    n_strikes : int
        Strikes nearest the forward whose parity forwards are averaged (median). ``3``: as the
        closed parity-spread study, enough to damp one stale quote.
    back_target_days, back_min_gap_days, back_max_gap_days : int
        Back expiry: nearest T1 + 35 days inside [T1 + 21, T1 + 120]. A gap of a month makes a
        5 bp forward error worth about 0.6% a year of borrow; much longer gaps reach expiries
        with few near-the-money quotes in 2013-16.
    div_lookback_days : int
        A regular dividend is projected only if one went ex within this many days before entry.
        ``400``: one annual payer's cycle plus slack.
    default_spacing_days : float
        Spacing used when fewer than two prior ex-dates exist. ``91``: quarterly.
    min_div : float
        Smallest CRSP-recovered dividend, USD. ``0.005``: L1 and E4's floor for rounding.
    special_ratio : float
        A prior dividend above this multiple of the median of its predecessors is not projected.
        ``2.0``: L1's special-dividend ratio.
    act360_to_365 : float
        DFF is quoted ACT/360; the parity discounting uses ACT/365.
    """

    n_strikes: int = 3
    back_target_days: int = 35
    back_min_gap_days: int = 21
    back_max_gap_days: int = 120
    div_lookback_days: int = 400
    default_spacing_days: float = 91.0
    min_div: float = 0.005
    special_ratio: float = 2.0
    act360_to_365: float = 365.0 / 360.0


BC = BorrowConfig()


# ── dividends (causal projection) ───────────────────────────────────────────


def _div_history() -> dict[str, list[tuple[pd.Timestamp, float]]]:
    """Ex-date and amount per ticker: CRSP-recovered (2011-24) and the cached 2025-26 file."""
    b = pd.read_parquet(BASE, columns=["ticker", "permno"]).dropna()
    perm_to_tick = b.drop_duplicates("permno").set_index("permno")["ticker"].to_dict()
    c = pd.read_parquet(CRSP)
    c["date"] = pd.to_datetime(c["date"])
    for col in ("prc", "ret", "cfacpr"):
        c[col] = pd.to_numeric(c[col], errors="coerce").astype(float)
    c["prc"] = c["prc"].abs()
    c = c.sort_values(["permno", "date"])
    g = c.groupby("permno")
    c["div"] = (1 + c["ret"]) * g["prc"].shift(1) - c["prc"]
    c.loc[c["cfacpr"] != g["cfacpr"].shift(1), "div"] = np.nan
    e = c[c["div"] > BC.min_div]
    hist: dict[str, list[tuple[pd.Timestamp, float]]] = {}
    for p, d, x in zip(e["permno"], e["date"], e["div"], strict=True):
        t = perm_to_tick.get(float(p))
        if t is not None:
            hist.setdefault(t, []).append((pd.Timestamp(d), float(x)))
    y = pd.read_parquet(YDIV)
    for t, d, x in zip(y["ticker"], pd.to_datetime(y["ex_date"]), y["dividend"], strict=True):
        if pd.Timestamp(d) > pd.Timestamp("2024-12-31"):
            hist.setdefault(t, []).append((pd.Timestamp(d), float(x)))
    return {t: sorted(v) for t, v in hist.items()}


def projected_divs(
    hist: list[tuple[pd.Timestamp, float]], entry: pd.Timestamp, lo: pd.Timestamp, hi: pd.Timestamp
) -> tuple[float, float]:
    """Regular dividends projected into (lo, hi] from ex-dates strictly before ``entry``.

    Returns the sum and the distance in days from any projected ex-date in [entry, hi + 30] to
    the nearer of ``lo`` and ``hi`` (inf if none), the timing-ambiguity measure.
    """
    past = [(d, x) for d, x in hist if d < entry]
    if not past or (entry - past[-1][0]).days > BC.div_lookback_days:
        return 0.0, float("inf")
    amts = [x for _, x in past[-5:]]
    last_amt = amts[-1]
    if len(amts) > 1 and last_amt > BC.special_ratio * float(np.median(amts[:-1])):
        last_amt = float(np.median(amts[:-1]))
    dates = [d for d, _ in past[-5:]]
    gaps = np.diff([d.value for d in dates]) / 86400e9
    gaps = gaps[gaps > 20]  # a special paid beside a regular dividend is not a cycle
    sp = float(np.median(gaps[-4:])) if gaps.size else BC.default_spacing_days
    total, k, last, edge = 0.0, 1, dates[-1], float("inf")
    while True:
        nxt = last + pd.Timedelta(days=round(k * sp))
        if nxt > hi + pd.Timedelta(days=30):
            break
        if nxt > entry:
            edge = min(edge, abs((nxt - lo).days), abs((nxt - hi).days))
        if lo < nxt <= hi and nxt > entry:
            total += last_amt
        k += 1
    return total, edge


def realised_divs(
    hist: list[tuple[pd.Timestamp, float]], lo: pd.Timestamp, hi: pd.Timestamp
) -> float:
    """Recovered dividends with ex-date in (lo, hi]: a diagnostic of the projection only."""
    return float(sum(x for d, x in hist if lo < d <= hi))


# ── parity forwards ─────────────────────────────────────────────────────────


def _forwards(path: Path, entry: pd.Timestamp, r: float, f_guess: float) -> pd.DataFrame:
    """Parity forward per expiry from two-sided mids on the strikes nearest the forward."""
    c = pd.read_parquet(path, columns=["symbol", "bid_px_00", "ask_px_00"])
    s = c["symbol"].str[-15:]
    c = c.assign(
        exp=pd.to_datetime("20" + s.str[:6], format="%Y%m%d"),
        cp=s.str[6],
        k=s.str[7:].astype(float) / 1000.0,
    )
    c = c[(c["bid_px_00"] > 0) & (c["ask_px_00"] >= c["bid_px_00"])]
    c = c.assign(mid=(c["bid_px_00"] + c["ask_px_00"]) / 2.0)
    w = c.pivot_table(index=["exp", "k"], columns="cp", values="mid", aggfunc="first")
    if not {"C", "P"} <= set(w.columns):
        return pd.DataFrame()
    w = w.dropna(subset=["C", "P"]).reset_index()
    rows = []
    for exp, g in w.groupby("exp"):
        tau = (exp - entry).days / 365.0
        if tau <= 0:
            continue
        fk = g["k"] + (g["C"] - g["P"]) * np.exp(r * tau)
        f0 = float(np.median(fk))
        near = g.assign(fk=fk, dist=(g["k"] - f0).abs()).nsmallest(BC.n_strikes, "dist")
        rows.append(
            {"exp": exp, "tau": tau, "F": float(near["fk"].median()), "n_k": int(len(near))}
        )
    return pd.DataFrame(rows)


_HIST: dict[str, list[tuple[pd.Timestamp, float]]] = {}
_DFF: pd.Series | None = None


def _init() -> None:
    global _HIST, _DFF
    _HIST = _div_history()
    r = pd.read_csv(DFF, parse_dates=["observation_date"]).set_index("observation_date")["DFF"]
    r = r.astype(float) / 100.0
    _DFF = r.reindex(pd.date_range(r.index.min(), r.index.max(), freq="D")).ffill()


def one(args: tuple[str, pd.Timestamp, pd.Timestamp, float]) -> dict:
    ticker, entry, expiry, f_guess = args
    out: dict = {"ticker": ticker, "entry_date": entry}
    path = CHAINS / f"{ticker}_{entry:%Y-%m-%d}.parquet"
    if not path.exists():
        return {**out, "b_status": "no_chain"}
    assert _DFF is not None
    r = float(_DFF.get(entry, np.nan)) * BC.act360_to_365
    fw = _forwards(path, entry, r, f_guess)
    if fw.empty:
        return {**out, "b_status": "no_two_sided"}
    front = fw[fw["exp"] == expiry]
    if front.empty:
        return {**out, "b_status": "no_front_expiry"}
    t1 = expiry
    lo, hi = t1 + pd.Timedelta(days=BC.back_min_gap_days), t1 + pd.Timedelta(
        days=BC.back_max_gap_days
    )
    back = fw[(fw["exp"] >= lo) & (fw["exp"] <= hi)]
    if back.empty:
        return {**out, "b_status": "no_back_expiry"}
    tgt = t1 + pd.Timedelta(days=BC.back_target_days)
    bk = back.iloc[int(np.argmin((back["exp"] - tgt).abs().to_numpy()))]
    f1, f2 = float(front["F"].iloc[0]), float(bk["F"])
    h = _HIST.get(ticker, [])
    dgap, edge = projected_divs(h, entry, t1, pd.Timestamp(bk["exp"]))
    dreal = realised_divs(h, t1, pd.Timestamp(bk["exp"]))
    dt = float(bk["tau"] - front["tau"].iloc[0])
    if not (f1 - dgap > 0 and f2 > 0):
        return {**out, "b_status": "bad_forward"}
    b = r - np.log(f2 / (f1 - dgap)) / dt
    return {
        **out,
        "b_status": "ok",
        "borrow": float(b),
        "F1": f1,
        "F2": f2,
        "dgap": dgap,
        "div_edge_days": edge,
        "dgap_realised_diag": dreal,
        "borrow_realised_diag": float(r - np.log(f2 / (f1 - dreal)) / dt) if f1 > dreal else np.nan,
        "dt_years": dt,
        "n_k1": int(front["n_k"].iloc[0]),
        "n_k2": int(bk["n_k"]),
        "r_cc": r,
        "lnF1_fwd": float(np.log(f1 / f_guess)) if f_guess > 0 else np.nan,
    }


def main() -> None:
    b = pd.read_parquet(BASE, columns=["ticker", "entry_date", "expiry", "front_fwd"])
    jobs = [
        (t, pd.Timestamp(e), pd.Timestamp(x), float(f))
        for t, e, x, f in zip(
            b["ticker"], b["entry_date"], b["expiry"], b["front_fwd"], strict=True
        )
    ]
    with ProcessPoolExecutor(max_workers=6, initializer=_init) as ex:
        rows = list(ex.map(one, jobs, chunksize=50))
    d = pd.DataFrame(rows)
    print("funnel (b_status):")
    print(d["b_status"].value_counts().to_string())
    ok = d[d["b_status"] == "ok"]
    print(
        f"front forward against the panel's front_fwd: median |ln| "
        f"{np.nanmedian(np.abs(ok['lnF1_fwd'])) * 1e4:.2f} bp, "
        f"p99 {np.nanpercentile(np.abs(ok['lnF1_fwd']), 99) * 1e4:.1f} bp"
    )
    q = ok["borrow"].quantile([0.01, 0.1, 0.25, 0.5, 0.75, 0.9, 0.99])
    print("implied borrow quantiles (annual, cc):", q.round(4).to_dict())
    print(f"events with projected dividends in the gap: {(ok['dgap'] > 0).sum()}")
    tmp = OUT.with_suffix(".tmp")
    d.to_parquet(tmp)
    tmp.replace(OUT)
    print(f"wrote {OUT} ({len(d)} rows)")


if __name__ == "__main__":
    main()
