"""
study.py
Index ETF straddles across scheduled events, held one session or overnight: families B1, B2, B3
and the SPY macro families A1, A2 (amendment 03), scored exactly as frozen in ``prereg.md``.

Every trade is priced from OPRA ``cbbo-1m`` quotes at the touch (sell at the bid, buy at the ask).
Returns are per unit of the entry mid premium P0 of the straddle.

Usage
-----
    python research/off_earnings/2026-11-01-index-event-crush/study.py
    python research/off_earnings/2026-11-01-index-event-crush/study.py --build-only

References
----------
Carr, P. and Wu, L. (2009). Variance risk premiums. Review of Financial Studies 22(3), 1311-1341.
Dubinsky, A., Johannes, M., Kaeck, A. and Seeger, N. J. (2019). Option pricing of earnings
announcement risks. Review of Financial Studies 32(2), 646-687.
Muravyev, D. and Ni, X. (2020). Why do option returns change sign from day to night? Journal of
Financial Economics 136(1), 219-238.
Politis, D. N. and Romano, J. P. (1992). A circular block-resampling procedure for stationary
data. In Exploring the Limits of Bootstrap, Wiley, 263-270.
Wright, J. H. (2021). Event-day options. NBER Working Paper 28306.
"""

from __future__ import annotations

import argparse
import json
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from earnings_iv_crush.engine.stats import deflated_sharpe_ratio, nyse_sessions  # noqa: E402
from earnings_iv_crush.research.protocol import (  # noqa: E402
    date_clustered_ci,
    per_trade_sharpe,
    verify_prereg,
)

# ── frozen constants (prereg.md) ─────────────────────────────────────────────

HERE = Path(__file__).resolve().parent
PREREG = HERE / "prereg.md"
RECORD = ROOT / "outputs" / "research" / f"prereg_{HERE.name}.json"
AMEND = ROOT / "research" / "off_earnings" / "preregs" / "spy_macro_and_runup_amendment_03.md"
OUT = ROOT / "outputs" / "research" / HERE.name
CHAINS = ROOT / "data" / "cache" / "index_chains"
MACRO = ROOT / "data" / "cache" / "index_events" / "macro_releases_2016_2026.csv"
MEGACAP = ROOT / "data" / "cache" / "index_events" / "megacap_amc_releases_2016_2026.csv"
SPY_MACRO_FROZEN = ROOT / "data" / "cache" / "spy_macro" / "releases.csv"

TICKERS = ("SPY", "QQQ", "IWM")
START, END = "2016-01-04", "2026-10-30"
BLOCKS = {
    "P": ("2016-01-04", "2018-12-31"),
    "M": ("2019-01-02", "2024-12-31"),
    "C": ("2025-01-02", "2026-10-30"),
}
COMMISSION_PER_SHARE = 0.0065  # USD 0.65 per contract per side
MARGIN_SPOT_FRAC = 0.15  # broad-based index short straddle approximation (secondary basis)
N_BOOT, SEED = 5000, 0
BLOCK_LEN = 10  # sessions, circular block bootstrap for B1 and B3
MATCH_WINDOW = 60  # sessions either side, B2 and A
MIN_CONTROLS = 5
A_TENOR_TOL = 3  # calendar days, A families (original prereg)
A_CI = 0.975  # Bonferroni over A1 and A2
N_TRIALS = 1549
SR_TRIALS_STD = 0.127475  # programme convention (per-trade Sharpe spread across trials)


# ── quotes ───────────────────────────────────────────────────────────────────


def load_chain(ticker: str, day: pd.Timestamp, snap: str) -> pd.DataFrame | None:
    """One snapshot: last record per contract, parsed. None when the file is missing or empty."""
    p = CHAINS / f"{ticker}_{day.date()}_{snap}.parquet"
    if not p.exists():
        return None
    df = pd.read_parquet(p)
    if df.empty:
        return None
    df = df.sort_values("ts_recv").groupby("symbol", as_index=False).last()
    sym = df["symbol"].astype(str)
    out = pd.DataFrame(
        {
            "expiry": pd.to_datetime(sym.str[6:12], format="%y%m%d"),
            "cp": sym.str[12],
            "strike": sym.str[13:21].astype(int) / 1000.0,
            "bid": df["bid_px_00"].astype(float),
            "ask": df["ask_px_00"].astype(float),
        }
    )
    return out


def _two_sided(df: pd.DataFrame) -> pd.Series:
    return (df["bid"] > 0) & (df["ask"] >= df["bid"]) & np.isfinite(df["ask"])


def build_trade(
    ticker: str, t: pd.Timestamp, t1: pd.Timestamp, exit_snap: str
) -> dict[str, object]:
    """One straddle from the 15:59 snapshot on t to ``exit_snap`` on t1 (prereg rules)."""
    base: dict[str, object] = {"ticker": ticker, "entry": t, "exit": t1, "exit_snap": exit_snap}
    e = load_chain(ticker, t, "1559")
    if e is None:
        return {**base, "status": "no_entry_snapshot"}
    x = load_chain(ticker, t1, exit_snap)
    if x is None:
        return {**base, "status": "no_exit_snapshot"}
    e2 = e[_two_sided(e)]
    piv = e2.pivot_table(index=["expiry", "strike"], columns="cp", values=["bid", "ask"])
    need = [("bid", "C"), ("ask", "C"), ("bid", "P"), ("ask", "P")]
    if any(c not in piv.columns for c in need):
        # only one side of the chain is two-sided: no strike has both legs quoted
        return {**base, "status": "no_two_sided_pair"}
    piv = piv[need].dropna()
    if piv.empty:
        return {**base, "status": "no_two_sided_pair"}
    exps = sorted(x0 for x0 in piv.index.get_level_values(0).unique() if x0 > t1)
    if not exps:
        return {**base, "status": "no_expiry_after_exit"}
    exp = exps[0]
    sub = piv.loc[exp]
    cmid = (sub[("bid", "C")] + sub[("ask", "C")]) / 2
    pmid = (sub[("bid", "P")] + sub[("ask", "P")]) / 2
    k = float((cmid - pmid).abs().idxmin())
    c0b, c0a = float(sub.loc[k, ("bid", "C")]), float(sub.loc[k, ("ask", "C")])
    p0b, p0a = float(sub.loc[k, ("bid", "P")]), float(sub.loc[k, ("ask", "P")])
    p0 = (c0b + c0a) / 2 + (p0b + p0a) / 2
    fwd = k + float(cmid.loc[k] - pmid.loc[k])
    leg = x[(x["expiry"] == exp) & (x["strike"] == k)].set_index("cp")
    rec: dict[str, object] = {
        **base,
        "expiry": exp,
        "strike": k,
        "dte": int((exp - t).days),
        "weekday": int(t.weekday()),
        "p0": p0,
        "fwd0": fwd,
        "c0b": c0b,
        "c0a": c0a,
        "p0b": p0b,
        "p0a": p0a,
    }
    for cp, nm in (("C", "c1"), ("P", "p1")):
        rec[f"{nm}b"] = float(leg.loc[cp, "bid"]) if cp in leg.index else np.nan
        rec[f"{nm}a"] = float(leg.loc[cp, "ask"]) if cp in leg.index else np.nan
    if not (rec["c1a"] > 0 and rec["p1a"] > 0):  # type: ignore[operator]
        return {**rec, "status": "no_exit_ask"}
    return {**rec, "status": "ok"}


def _returns(df: pd.DataFrame) -> pd.DataFrame:
    """Short/long touch and mid returns per unit P0, plus the margin basis (prereg)."""
    d = df.copy()
    comm = 4 * COMMISSION_PER_SHARE
    entry_bid = d["c0b"] + d["p0b"]
    entry_ask = d["c0a"] + d["p0a"]
    exit_bid = d["c1b"] + d["p1b"]
    exit_ask = d["c1a"] + d["p1a"]
    two_sided_exit = (d["c1b"] > 0) & (d["p1b"] > 0)
    d["short_touch"] = (entry_bid - exit_ask) / d["p0"]
    d["short_touch_net"] = (entry_bid - exit_ask - comm) / d["p0"]
    d["long_touch"] = np.where(two_sided_exit, (exit_bid - entry_ask) / d["p0"], np.nan)
    mid1 = ((d["c1b"] + d["c1a"]) + (d["p1b"] + d["p1a"])) / 2
    d["short_mid"] = np.where(two_sided_exit, (d["p0"] - mid1) / d["p0"], np.nan)
    d["long_mid"] = -d["short_mid"]
    margin = d["p0"] + MARGIN_SPOT_FRAC * d["fwd0"]
    d["short_touch_net_rom"] = (entry_bid - exit_ask - comm) / margin
    return d


def build_all(workers: int = 8) -> pd.DataFrame:
    sessions = nyse_sessions(pd.Timestamp(START), pd.Timestamp(END))
    jobs = [
        (tk, sessions[i], sessions[i + 1], snap)
        for tk in TICKERS
        for i in range(len(sessions) - 1)
        for snap in ("1559", "1000")
    ]
    with ProcessPoolExecutor(max_workers=workers) as ex:
        rows = list(ex.map(_job, jobs, chunksize=64))
    return pd.DataFrame(rows)


def _job(j: tuple[str, pd.Timestamp, pd.Timestamp, str]) -> dict[str, object]:
    return build_trade(*j)


# ── inference ────────────────────────────────────────────────────────────────


def block_ci(x: np.ndarray, ci: float = 0.95) -> tuple[float, float]:
    """Circular moving-block bootstrap percentile interval for the mean (series in time order)."""
    x = np.asarray(x, dtype=float)
    n = x.size
    rng = np.random.default_rng(SEED)
    nb = int(np.ceil(n / BLOCK_LEN))
    starts = rng.integers(0, n, size=(N_BOOT, nb))
    idx = (starts[:, :, None] + np.arange(BLOCK_LEN)[None, None, :]).reshape(N_BOOT, -1)[:, :n] % n
    means = x[idx].mean(axis=1)
    a = (1 - ci) / 2
    return float(np.quantile(means, a)), float(np.quantile(means, 1 - a))


def _mean(v: np.ndarray) -> float:
    return float(np.mean(v))


def block_of(day: pd.Timestamp) -> str:
    for b, (lo, hi) in BLOCKS.items():
        if pd.Timestamp(lo) <= day <= pd.Timestamp(hi):
            return b
    raise ValueError(f"{day.date()} outside every block")


def summarise_series(d: pd.DataFrame, col: str) -> dict[str, object]:
    d = d.sort_values("entry")
    x = d[col].to_numpy(dtype=float)
    x = x[np.isfinite(x)]
    lo, hi = block_ci(x)
    iid = date_clustered_ci(d[col], d["entry"], _mean)
    years = (d["entry"].max() - d["entry"].min()).days / 365.25
    tpy = len(x) / years if years > 0 else float("nan")
    sr = per_trade_sharpe(x)
    return {
        "n": int(x.size),
        "mean": float(x.mean()),
        "block_ci": [lo, hi],
        "iid_ci": [iid.low, iid.high],
        "sharpe_per_trade": sr,
        "trades_per_year": tpy,
        "sharpe_annualised_own_cadence": sr * np.sqrt(tpy),
        "hit_rate": float((x > 0).mean()),
    }


def tail(d: pd.DataFrame, col: str) -> dict[str, object]:
    d = d.sort_values("entry")
    pnl = (d[col] * d["p0"]).to_numpy()  # USD per share of one straddle
    eq = np.cumsum(pnl)
    dd = float((np.maximum.accumulate(eq) - eq).max())
    worst = d.nsmallest(5, col)[["entry", col]]
    q = np.quantile(pnl, 0.01)
    x = d[col].to_numpy()
    return {
        "worst5": [(str(r.entry.date()), float(getattr(r, col))) for r in worst.itertuples()],
        "max_drawdown_in_mean_p0": dd / float(d["p0"].mean()),
        "skew": float(pd.Series(x).skew()),
        "share_pnl_worst_1pct": float(pnl[pnl <= q].sum() / pnl.sum()) if pnl.sum() else np.nan,
        "total_pnl_in_mean_p0": float(pnl.sum() / d["p0"].mean()),
    }


def series_family(d: pd.DataFrame, col: str) -> dict[str, object]:
    """B1/B3 rule: M passes with block CI > 0; P and C each mean > 0; P+C pooled block CI > 0."""
    res: dict[str, object] = {}
    for b in ("P", "M", "C"):
        res[b] = summarise_series(d[d["block"] == b], col)
    pc = d[d["block"].isin(["P", "C"])]
    res["P+C"] = summarise_series(pc, col)
    m = res["M"]
    disc = m["mean"] > 0 and m["block_ci"][0] > 0  # type: ignore[index,operator]
    val = (
        res["P"]["mean"] > 0  # type: ignore[index,operator]
        and res["C"]["mean"] > 0  # type: ignore[index,operator]
        and res["P+C"]["block_ci"][0] > 0  # type: ignore[index]
    )
    res["verdict"] = "PASS" if disc and val else ("in-sample only" if disc else "FAIL")
    return res


def matched(
    ev: pd.DataFrame, ctl: pd.DataFrame, col: str, keys: list[str], tenor_tol: int | None
) -> pd.DataFrame:
    """Event return minus the mean of controls matched on ``keys``/tenor within the window."""
    pos = {d: i for i, d in enumerate(nyse_sessions(pd.Timestamp(START), pd.Timestamp(END)))}
    ctl = ctl.assign(_pos=ctl["entry"].map(pos))
    rows = []
    for r in ev.itertuples():
        p = pos[r.entry]
        c = ctl[(ctl["_pos"] - p).abs() <= MATCH_WINDOW]
        for k in keys:
            c = c[c[k] == getattr(r, k)]
        if tenor_tol is not None:
            c = c[(c["dte"] - r.dte).abs() <= tenor_tol]
        c = c[np.isfinite(c[col])]
        if len(c) < MIN_CONTROLS or not np.isfinite(getattr(r, col)):
            rows.append({"entry": r.entry, "diff": np.nan, "n_ctl": len(c)})
            continue
        rows.append(
            {
                "entry": r.entry,
                "event": float(getattr(r, col)),
                "control": float(c[col].mean()),
                "diff": float(getattr(r, col) - c[col].mean()),
                "n_ctl": len(c),
            }
        )
    return pd.DataFrame(rows)


# ── families ─────────────────────────────────────────────────────────────────


def family_b2(q: pd.DataFrame, macro_days: set[pd.Timestamp]) -> dict[str, object]:
    mc = pd.read_csv(MEGACAP, parse_dates=["release_date"])
    nights = set(mc["release_date"])
    is_ev = q["entry"].isin(nights)
    exit_macro = q["exit"].isin(macro_days)
    funnel = {
        "qqq_trades_ok": int(len(q)),
        "event_nights_in_calendar": len(nights),
        "event_trades": int(is_ev.sum()),
        "event_trades_exit_on_macro_day_excluded": int((is_ev & exit_macro).sum()),
    }
    ev = q[is_ev & ~exit_macro]
    ctl = q[~is_ev & ~exit_macro]
    col = "short_touch_net"
    pr = matched(ev, ctl, col, ["dte", "weekday"], None)
    funnel["events_with_5_controls"] = int(pr["diff"].notna().sum())
    pr["block"] = pr["entry"].map(block_of)
    res: dict[str, object] = {"funnel": funnel}
    for b, sel in (("P", ["P"]), ("M", ["M"]), ("C", ["C"]), ("P+C", ["P", "C"])):
        s = pr[pr["block"].isin(sel) & pr["diff"].notna()]
        e_own = ev[ev["block"].isin(sel)]
        if len(s) < 3:
            res[b] = {"n": int(len(s))}
            continue
        ci = date_clustered_ci(s["diff"], s["entry"], _mean)
        res[b] = {
            "n": ci.n,
            "mean_diff": ci.point,
            "ci": [ci.low, ci.high],
            "event_mean": float(s["event"].mean()),
            "control_mean": float(s["control"].mean()),
            "event_book_mean_all": float(e_own[col].mean()),
            "event_book_sharpe": per_trade_sharpe(e_own[col]),
        }
    m = res["M"]
    ok_m = (
        isinstance(m, dict)
        and m.get("mean_diff", -1) > 0
        and m["ci"][0] > 0
        and m["event_book_mean_all"] > 0
    )
    pc = res["P+C"]
    ok_v = (
        isinstance(pc, dict)
        and "ci" in pc
        and pc["ci"][0] > 0
        and res["P"].get("mean_diff", -1) > 0  # type: ignore[union-attr]
        and res["C"].get("mean_diff", -1) > 0  # type: ignore[union-attr]
    )
    res["verdict"] = "PASS" if ok_m and ok_v else ("in-sample only" if ok_m else "FAIL")
    # mechanism: realised one-night |log move| on event vs matched control nights
    for nm, frame in (("event", ev), ("control", ctl)):
        mv = np.log(frame["fwd1"] / frame["fwd0"]).abs()
        res[f"abs_move_{nm}_M"] = float(mv[frame["block"] == "M"].mean())
    res["implied_move_event_M"] = float(
        (0.8 * ev.loc[ev["block"] == "M", "p0"] / ev.loc[ev["block"] == "M", "fwd0"]).mean()
    )
    res["implied_move_control_M"] = float(
        (0.8 * ctl.loc[ctl["block"] == "M", "p0"] / ctl.loc[ctl["block"] == "M", "fwd0"]).mean()
    )
    return res


def family_a(spy: pd.DataFrame, rel: pd.DataFrame, block_sel: list[str]) -> dict[str, object]:
    """Amendment 03: A1 short across CPI/NFP, A2 long across FOMC-only, 97.5% intervals."""
    s = spy[spy["block"].isin(block_sel)]
    rel_days = set(rel["date"])
    ctl = s[~s["exit"].isin(rel_days)]
    by_kind = rel.groupby("date")["kind"].apply(set)
    a1_days = {d for d, k in by_kind.items() if k & {"cpi", "nfp"}}
    a2_days = {d for d, k in by_kind.items() if "fomc" in k and not (k & {"cpi", "nfp"})}
    out: dict[str, object] = {}
    for fam, days, col in (("A1", a1_days, "short_touch"), ("A2", a2_days, "long_touch")):
        ev = s[s["exit"].isin(days)].copy()
        ev = ev[np.isfinite(ev[col])]
        absd = date_clustered_ci(ev[col], ev["exit"], _mean, ci=A_CI)
        pr = matched(ev, ctl, col, [], A_TENOR_TOL)
        pr = pr[pr["diff"].notna()]
        pd_ci = date_clustered_ci(pr["diff"], pr["entry"], _mean, ci=A_CI) if len(pr) > 2 else None
        net_col = "short_touch_net" if fam == "A1" else None
        out[fam] = {
            "n_events_priced": int(len(ev)),
            "abs_mean": absd.point,
            "abs_ci975": [absd.low, absd.high],
            "paired_n": int(len(pr)),
            "paired_mean": pd_ci.point if pd_ci else np.nan,
            "paired_ci975": [pd_ci.low, pd_ci.high] if pd_ci else None,
            "sharpe_per_trade": per_trade_sharpe(ev[col]),
            "mid_mean": float(ev["short_mid" if fam == "A1" else "long_mid"].mean()),
            "net_of_commission_mean": (
                float(ev[net_col].mean())
                if net_col
                else float((ev["long_touch"] - 4 * COMMISSION_PER_SHARE / ev["p0"]).mean())
            ),
        }
        passed = absd.low > 0 and pd_ci is not None and pd_ci.low > 0 and pd_ci.point > 0
        gen = absd.low > 0 and not passed
        out[fam]["verdict"] = (  # type: ignore[index]
            "PASS" if passed else ("generic premium, not event-specific" if gen else "FAIL")
        )
    return out


# ── main ─────────────────────────────────────────────────────────────────────


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--build-only", action="store_true")
    ap.add_argument("--workers", type=int, default=8)
    a = ap.parse_args()

    sha = verify_prereg(PREREG, RECORD)
    rec = json.loads(RECORD.read_text(encoding="utf-8"))
    from earnings_iv_crush.research.protocol import sha256_file

    for path, key in (
        (AMEND, "amendment_sha256"),
        (MACRO, "calendar_macro_sha256"),
        (MEGACAP, "calendar_megacap_sha256"),
        (SPY_MACRO_FROZEN, "calendar_spy_macro_frozen_sha256"),
    ):
        if sha256_file(path) != rec[key]:
            raise ValueError(f"{path} changed after freezing ({key})")
    print(f"  prereg verified {sha[:12]}; amendment and calendars match the record")

    OUT.mkdir(parents=True, exist_ok=True)
    trades_path = OUT / "trades.parquet"
    raw = build_all(a.workers)
    raw.to_parquet(trades_path)
    funnel = raw.groupby(["ticker", "exit_snap", "status"]).size().unstack(fill_value=0)
    print("  funnel (trades by status):")
    print(funnel.to_string())
    (OUT / "funnel.csv").write_text(funnel.to_csv(), encoding="utf-8")
    if a.build_only:
        return

    ok = raw[raw["status"] == "ok"].copy()
    if ok.empty:
        raise RuntimeError("no priced trades; refusing to score an empty book")
    ok["entry"] = pd.to_datetime(ok["entry"])
    ok["exit"] = pd.to_datetime(ok["exit"])
    ok = _returns(ok)
    ok["block"] = ok["entry"].map(block_of)
    # exit forward for the mechanism check: parity at exit where both legs are two-sided
    ok["fwd1"] = np.where(
        (ok["c1b"] > 0) & (ok["p1b"] > 0),
        ok["strike"] + (ok["c1b"] + ok["c1a"]) / 2 - (ok["p1b"] + ok["p1a"]) / 2,
        np.nan,
    )

    # attrition: dropped-at-exit vs kept, on |log move| of SPY close-to-close forward proxy
    drops = raw[raw["status"] == "no_exit_ask"]
    att = {"no_exit_ask": int(len(drops)), "ok": int(len(ok))}

    res: dict[str, object] = {"prereg_sha256": sha, "attrition": att}
    macro = pd.read_csv(MACRO, parse_dates=["date"])
    macro_days = set(macro["date"])

    close = ok[ok["exit_snap"] == "1559"]
    over = ok[ok["exit_snap"] == "1000"]
    for tk in TICKERS:
        c_tk, o_tk = close[close["ticker"] == tk], over[over["ticker"] == tk]
        res[f"B1_{tk}"] = series_family(c_tk, "short_touch_net")
        res[f"B3_{tk}"] = series_family(o_tk, "short_touch_net")
        res[f"B1_{tk}_mid"] = {
            b: float(c_tk.loc[c_tk.block == b, "short_mid"].mean()) for b in BLOCKS
        }
        res[f"B3_{tk}_mid"] = {
            b: float(o_tk.loc[o_tk.block == b, "short_mid"].mean()) for b in BLOCKS
        }
        res[f"B1_{tk}_rom_sharpe"] = {
            b: per_trade_sharpe(c_tk.loc[c_tk.block == b, "short_touch_net_rom"]) for b in BLOCKS
        }
        res[f"tail_B1_{tk}"] = tail(c_tk, "short_touch_net")
        res[f"tail_B3_{tk}"] = tail(o_tk, "short_touch_net")
        res[f"B1_{tk}_dsr"] = float(
            deflated_sharpe_ratio(
                c_tk["short_touch_net"].reset_index(drop=True), N_TRIALS, SR_TRIALS_STD
            )
        )
        res[f"B3_{tk}_dsr"] = float(
            deflated_sharpe_ratio(
                o_tk["short_touch_net"].reset_index(drop=True), N_TRIALS, SR_TRIALS_STD
            )
        )
        pair = c_tk.merge(o_tk, on=["entry"], suffixes=("_c", "_o"))
        res[f"B3_minus_B1_{tk}"] = {
            b: float(
                (
                    pair.loc[pair.block_c == b, "short_touch_net_o"]
                    - pair.loc[pair.block_c == b, "short_touch_net_c"]
                ).mean()
            )
            for b in BLOCKS
        }
    by_year = close.groupby([close["ticker"], close["entry"].dt.year])["short_touch_net"].agg(
        ["mean", "count"]
    )
    (OUT / "b1_by_year.csv").write_text(by_year.to_csv(), encoding="utf-8")
    by_dte = close[close.ticker == "SPY"].groupby("dte")["short_touch_net"].agg(["mean", "count"])
    (OUT / "b1_spy_by_dte.csv").write_text(by_dte.to_csv(), encoding="utf-8")

    res["B2"] = family_b2(close[close["ticker"] == "QQQ"], macro_days)

    spy_close = close[close["ticker"] == "SPY"]
    frozen = pd.read_csv(SPY_MACRO_FROZEN, parse_dates=["date"])
    res["A_M_frozen_calendar"] = family_a(spy_close, frozen, ["M"])
    res["A_confirmation_P_C"] = family_a(spy_close, macro, ["P", "C"])

    ok.to_parquet(OUT / "priced_trades.parquet")
    (OUT / "summary.json").write_text(json.dumps(res, indent=2, default=str), encoding="utf-8")
    for k in ("B1_SPY", "B3_SPY", "B2"):
        print(f"  {k}: {res[k]['verdict']}")  # type: ignore[index]
    for k in ("A_M_frozen_calendar",):
        for fam in ("A1", "A2"):
            print(f"  {fam} (2019-24): {res[k][fam]['verdict']}")  # type: ignore[index]
    print(f"  wrote {OUT}")


if __name__ == "__main__":
    main()
