"""
spill.py
Outcome construction for the E3 spillover trials (declared in diagnosis.log, entry 2).

Builds one trade per (peer, reaction date) from peer_nights.parquet and CRSP, and scores the
directional trials and the variance-ratio ceiling for a requested block of years. The block
argument is the only thing that differs between the discovery and held-out scorers.
"""

from __future__ import annotations

import sys
from collections.abc import Callable
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import lib  # noqa: E402

sys.path.insert(0, str(lib.ROOT))
from earnings_iv_crush.research.protocol import date_clustered_ci  # noqa: E402

N_FLIP = 5000
SEED = 0
CTRL_NEAR, CTRL_FAR = 6, 25  # control sessions for the variance ratio, either side
TZ_MIN, TZ_MAX = 3, 40  # sessions to the peer's own reaction for trial 2746
BP = 1e4


def _mean(x: np.ndarray) -> float:
    return float(np.mean(x))


class Panel:
    """CRSP returns and spreads as session-indexed matrices for fast lookups."""

    def __init__(self) -> None:
        d = lib.crsp()
        self.sess = pd.DatetimeIndex(sorted(d["date"].unique()))
        self.pos = {t: i for i, t in enumerate(self.sess)}
        self.perm = np.array(sorted(d["permno"].unique()))
        self.ppos = {p: i for i, p in enumerate(self.perm)}
        r = d.pivot(index="date", columns="permno", values="ret").reindex(self.sess)
        h = d.pivot(index="date", columns="permno", values="half_spread").reindex(self.sess)
        self.ret = r[self.perm].to_numpy(dtype=float)
        self.hs = h[self.perm].to_numpy(dtype=float)
        m = lib.market().reindex(self.sess)
        if m.isna().any():
            raise ValueError(f"market return missing on {int(m.isna().sum())} sessions")
        self.mkt = m.to_numpy(dtype=float)


def trades(pn: pd.DataFrame, P: Panel) -> pd.DataFrame:
    """One row per (peer, reaction date) with signal, costs and outcomes for every horizon."""
    pn = pn.copy()
    pn["i1"] = pn["exit_date"].map(P.pos)
    bi = pn["b_permno"].map(P.ppos)
    pi = pn["p_permno"].map(P.ppos)
    if pn["i1"].isna().any() or bi.isna().any() or pi.isna().any():
        raise ValueError("peer night outside the CRSP panel")
    i1 = pn["i1"].to_numpy(int)
    pn["b_abn"] = P.ret[i1, bi.to_numpy(int)] - P.mkt[i1]
    funnel = {"peer_nights": len(pn), "b_ret_missing": int(pn["b_abn"].isna().sum())}
    pn = pn.dropna(subset=["b_abn"])
    g = pn.groupby(["p_permno", "exit_date"], as_index=False).agg(
        p_ticker=("p_ticker", "first"), i1=("i1", "first"), b_abn=("b_abn", "mean"),
        n_reporters=("b_permno", "nunique"), lead=("lead", "max"),
        clear_long=("clear_long", "min"), p_next_report_d0=("p_next_report_d0", "min"),
        sic3=("sic3", "first"))
    funnel["peer_dates"] = len(g)
    # the |signal| floor applies to the directional trials only; the variance ratio (an option
    # bought before B reports) must use every peer date, since the buyer cannot see the signal
    g["signal_ok"] = g["b_abn"].abs() >= lib.MIN_ABS_SIGNAL
    funnel["signal_ge_1pct"] = int(g["signal_ok"].sum())
    g["s"] = np.sign(g["b_abn"])
    i1 = g["i1"].to_numpy(int)
    pj = g["p_permno"].map(P.ppos).to_numpy(int)
    n = len(P.sess)

    def _r(k: int) -> np.ndarray:
        idx = i1 + k
        ok = idx < n
        out = np.full(len(idx), np.nan)
        out[ok] = P.ret[idx[ok], pj[ok]] - P.mkt[idx[ok]]
        return out

    def _hs(k: int) -> np.ndarray:
        idx = np.minimum(i1 + k, n - 1)
        out = P.hs[idx, pj]
        out[i1 + k >= n] = np.nan
        return out

    hedge_rt = 2 * (lib.HEDGE_HALF_SPREAD_BP + lib.STOCK_FEE_BP) / BP
    fee_rt = 2 * lib.STOCK_FEE_BP / BP
    g["co_move"] = P.ret[i1, pj] - P.mkt[i1]  # peer's same-session hedged return
    g["raw_react"] = P.ret[i1, pj]
    g["h1"] = _r(1)
    g["cost1"] = _hs(0) + _hs(1) + fee_rt + hedge_rt
    g["h5"] = np.nansum(np.column_stack([_r(k) for k in range(1, 6)]), axis=1)
    g.loc[np.isnan(_r(5)), "h5"] = np.nan
    g["cost5"] = _hs(0) + _hs(5) + fee_rt + hedge_rt
    # Thomas-Zhang: hold to the close of the peer's own next reaction session (panel calendar,
    # which carries the session timing); a Compustat-only report earlier than that voids the row
    react_by = panel_reactions(P)
    nxt_any = pd.to_datetime(g["p_next_report_d0"])
    k_tz = np.full(len(g), np.nan)
    for j, p in enumerate(g["p_permno"].to_numpy()):
        arr = react_by.get(int(p))
        if arr is None:
            continue
        q_i = int(np.searchsorted(arr, i1[j], side="right"))
        if q_i >= len(arr):
            continue
        q = int(arr[q_i])
        k = q - i1[j]
        first_any = nxt_any.iloc[j]
        if pd.notna(first_any) and first_any < P.sess[q] - pd.Timedelta(days=lib.RDQ_CLEAR_DAYS + 5):
            continue  # another report window starts well before this panel reaction
        if TZ_MIN <= k <= TZ_MAX and q < n:
            k_tz[j] = k
    g["k_tz"] = k_tz
    tz = np.full(len(g), np.nan)
    ctz = np.full(len(g), np.nan)
    for j in np.flatnonzero(np.isfinite(k_tz)):
        k = int(k_tz[j])
        seg = P.ret[i1[j] + 1 : i1[j] + k + 1, pj[j]] - P.mkt[i1[j] + 1 : i1[j] + k + 1]
        if np.isfinite(seg).all():
            tz[j] = seg.sum()
            ctz[j] = P.hs[i1[j], pj[j]] + P.hs[i1[j] + k, pj[j]] + fee_rt + hedge_rt
    g["htz"], g["costtz"] = tz, ctz
    print(f"trade funnel: {funnel}; h1 finite {int(np.isfinite(g['h1']).sum())}, cost1 finite "
          f"{int(np.isfinite(g['cost1']).sum())}, h5 finite {int(np.isfinite(g['h5']).sum())}, "
          f"TZ finite {int(np.isfinite(g['htz']).sum())}")
    return g


def panel_reactions(P: Panel) -> dict[int, np.ndarray]:
    """Sorted reaction-session indices per permno from the panel calendars (any status)."""
    f = lib.events()[["ticker", "permno", "exit_date"]]
    t2p = f.groupby("ticker")["permno"].first()
    e = pd.read_parquet(lib.EVENTS_ALL, columns=["ticker", "exit_date"])
    e["permno"] = e["ticker"].map(t2p)
    e = e.dropna(subset=["permno"])
    from earnings_iv_crush.data.real_events import entry_exit_dates

    cal = pd.read_parquet(lib.CALENDAR_BROAD, columns=["ticker", "announce_date", "session"])
    cal = cal[cal["session"].isin(["amc", "bmo"])].copy()
    cal["permno"] = cal["ticker"].map(t2p)
    cal = cal.dropna(subset=["permno"])
    cal["exit_date"] = [entry_exit_dates(pd.Timestamp(a), s)[1]
                        for a, s in zip(cal["announce_date"], cal["session"], strict=True)]
    allr = pd.concat([f[["permno", "exit_date"]], e[["permno", "exit_date"]],
                      cal[["permno", "exit_date"]]])
    allr["exit_date"] = pd.to_datetime(allr["exit_date"]).dt.normalize()
    allr = allr[allr["exit_date"].isin(P.pos)].drop_duplicates()
    allr["i"] = allr["exit_date"].map(P.pos).astype(int)
    return {int(k): np.sort(v["i"].to_numpy()) for k, v in allr.groupby("permno")}


def sign_flip_percentile(y: np.ndarray, dates: np.ndarray, *, seed: int = SEED) -> float:
    """Percentile of mean(y) among means with every date's signs flipped together."""
    rng = np.random.default_rng(seed)
    u, inv = np.unique(dates, return_inverse=True)
    obs = y.mean()
    draws = np.empty(N_FLIP)
    for b in range(N_FLIP):
        f = rng.choice([-1.0, 1.0], size=len(u))
        draws[b] = (y * f[inv]).mean()
    return float((draws < obs).mean() * 100)


def score_direction(g: pd.DataFrame, trial: int, ycol: str, ccol: str, sign: float,
                    mask: np.ndarray | None = None, weighted: bool = False) -> dict:
    """Gross and net per-trade mean in bp with date-clustered CIs and the sign-flip null.

    ``weighted`` (trial 2751) sizes each trade by |b_abn| / mean|b_abn| over the scored set, so
    the mean is per unit of average notional and cost scales with the size.
    """
    m = np.isfinite(g[ycol]) & np.isfinite(g[ccol]) & g["signal_ok"]
    if mask is not None:
        m &= mask
    d = g[m]
    if len(d) < 30:
        raise ValueError(f"trial {trial}: only {len(d)} scoreable trades")
    w = np.ones(len(d))
    if weighted:
        a = d["b_abn"].abs().to_numpy()
        w = a / a.mean()
    gross = w * sign * d["s"].to_numpy() * d[ycol].to_numpy()
    net = gross - w * d[ccol].to_numpy()
    dates = d["exit_date"].to_numpy()
    cg = date_clustered_ci(gross * BP, dates, stat=_mean)
    cn = date_clustered_ci(net * BP, dates, stat=_mean)
    sh = date_clustered_ci(net, dates)  # per-trade Sharpe on net
    pct = sign_flip_percentile(gross, dates)
    passed = bool(cn.low > 0 and pct >= 97.5)
    killed = bool((cg.low <= 0 <= cg.high) or cn.high < 0)
    return {
        "trial": trial, "n": cn.n, "dates": cn.clusters,
        "gross_bp": cg.point, "gross_lo": cg.low, "gross_hi": cg.high,
        "cost_bp": float((w * d[ccol].to_numpy()).mean() * BP),
        "net_bp": cn.point, "net_lo": cn.low, "net_hi": cn.high,
        "sharpe_net": sh.point, "sharpe_lo": sh.low, "sharpe_hi": sh.high,
        "flip_pct": pct, "pass": passed, "kill": killed,
    }


def transfer_check(g: pd.DataFrame) -> dict:
    """Right driver: the peer's same-session hedged co-move signed by s, and the market leg."""
    d = g[np.isfinite(g["co_move"]) & g["signal_ok"]]
    co = d["s"].to_numpy() * d["co_move"].to_numpy()
    c = date_clustered_ci(co * BP, d["exit_date"].to_numpy(), stat=_mean)
    beta = np.polyfit(d["b_abn"], d["co_move"], 1)[0]
    return {"co_move_bp": c.point, "lo": c.low, "hi": c.high, "n": c.n, "slope": float(beta)}


def own_report_sessions(P: Panel) -> set[tuple[int, int]]:
    """(permno, session) pairs within 2 before to 5 after any own report (trial 2749 control)."""
    rp = lib.all_report_dates()
    out: set[tuple[int, int]] = set()
    sv = P.sess.values
    for p, d0, d1 in zip(rp["permno"], rp["d0"], rp["d1"], strict=True):
        a = int(np.searchsorted(sv, np.datetime64(d0), side="left")) - 2
        b = int(np.searchsorted(sv, np.datetime64(d1), side="right")) + 5
        for i in range(max(a, 0), min(b, len(sv))):
            out.add((int(p), i))
    return out


def variance_ratio(g: pd.DataFrame, P: Panel, react: pd.DataFrame,
                   adjust: bool, own: set[tuple[int, int]] | None = None
                   ) -> tuple[dict, pd.DataFrame]:
    """Trial 2747: peer's reaction-session r^2 over its matched control sessions' mean r^2.

    ``react`` holds every universe reaction session by SIC3 (and per permno), used to exclude
    control sessions on which the peer or any same-SIC3 universe name reacts. ``own`` (trial
    2749) further drops sessions near any of the peer's own reports.
    """
    busy_sic = {(s, i) for s, i in zip(react["sic3"], react["i1"], strict=True)}
    busy_p = {(p, i) for p, i in zip(react["permno"], react["i1"], strict=True)}
    if own is not None:
        busy_p |= own
    n = len(P.sess)
    ev2, ct2, keep = [], [], []
    for j, r in enumerate(g.itertuples(index=False)):
        pj = P.ppos[r.p_permno]
        x = P.ret[:, pj] - (P.mkt if adjust else 0.0)
        e = x[r.i1]
        idx = [r.i1 + k for k in range(-CTRL_FAR, CTRL_FAR + 1) if abs(k) >= CTRL_NEAR]
        idx = [i for i in idx if 0 <= i < n and (r.sic3, i) not in busy_sic
               and (r.p_permno, i) not in busy_p and np.isfinite(x[i])]
        if len(idx) < 10 or not np.isfinite(e):
            continue
        ev2.append(e * e)
        ct2.append(float(np.mean(x[idx] ** 2)))
        keep.append(j)
    d = g.iloc[keep].copy()
    d["e2"], d["c2"] = ev2, ct2
    keys = d["exit_date"].dt.normalize().to_numpy()
    u, inv = np.unique(keys, return_inverse=True)
    se = np.bincount(inv, weights=d["e2"].to_numpy())
    sc = np.bincount(inv, weights=d["c2"].to_numpy())
    rng = np.random.default_rng(SEED)
    boot = []
    for _ in range(N_FLIP):
        b = rng.integers(0, len(u), len(u))
        boot.append(se[b].sum() / sc[b].sum())
    vr = float(se.sum() / sc.sum())
    lo, hi = np.percentile(boot, [2.5, 97.5])
    return {"vr": vr, "lo": float(lo), "hi": float(hi), "n": len(d), "dates": len(u),
            "adjusted": adjust}, d


def reaction_sessions(P: Panel) -> pd.DataFrame:
    """Every universe event's reaction session index with SIC3, for control exclusion."""
    ev = lib.events()
    names = lib.sic_history()
    ev = ev[ev["exit_date"].isin(P.pos)].copy()
    ev["i1"] = ev["exit_date"].map(P.pos).astype(int)
    ev["sic"] = lib.sic_at(names, ev["permno"].to_numpy(), ev["entry_date"].to_numpy())
    ev = ev.dropna(subset=["sic"])
    ev["sic3"] = (ev["sic"] // 10 ** (4 - lib.SIC_DIGITS)).astype(int)
    return ev[["permno", "sic3", "i1"]]


def block(g: pd.DataFrame, years: tuple[int, int]) -> pd.DataFrame:
    y = g["exit_date"].dt.year
    out = g[(y >= years[0]) & (y <= years[1])].copy()
    if out.empty:
        raise ValueError(f"block {years} is empty")
    return out


def run(years: tuple[int, int], trials: list[int], log: Callable[[str], None]) -> list[dict]:
    """Score the requested trials on one block of years."""
    P = Panel()
    pn = pd.read_parquet(lib.HERE / "peer_nights.parquet")
    g = trades(block(pn, years), P)  # outcomes are never built outside the requested block
    log(f"block {years}: {len(g)} peer dates, {int(g['signal_ok'].sum())} with |signal| >= 1%, "
        f"on {g['exit_date'].nunique()} dates; "
        f"lead {int(g['lead'].sum())}; clear_long {int(g['clear_long'].sum())}; "
        f"TZ {int(np.isfinite(g['htz']).sum())}")
    tc = transfer_check(g)
    log(f"transfer check (peer same-session hedged co-move signed by s): {tc}")
    out = []
    spec = {
        2742: ("h1", "cost1", 1.0, None),
        2743: ("h1", "cost1", -1.0, None),
        2744: ("h1", "cost1", 1.0, g["lead"].to_numpy(bool)),
        2745: ("h5", "cost5", 1.0, g["clear_long"].to_numpy(bool)),
        2746: ("htz", "costtz", -1.0, None),
        2750: ("h1", "cost1", 1.0, (g["b_abn"].abs() >= 0.03).to_numpy()),
        2751: ("h1", "cost1", 1.0, None, True),
        2752: ("h1", "cost1", 1.0, (np.sign(g["co_move"]) == -g["s"]).to_numpy()),
    }
    for t in trials:
        if t in spec:
            r = score_direction(g, t, *spec[t])
            log(f"trial {t}: " + ", ".join(f"{k}={v:.4f}" if isinstance(v, float) else f"{k}={v}"
                                           for k, v in r.items()))
            out.append(r)
    if 2747 in trials or 2749 in trials:
        react = reaction_sessions(P)
        own = own_report_sessions(P) if 2749 in trials else None
        for t, o in ((2747, None), (2749, own)):
            if t not in trials:
                continue
            for adj in (False, True):
                r, _ = variance_ratio(g, P, react, adj, o)
                r["trial"] = t
                log(f"trial {t} variance ratio: {r}")
                out.append(r)
    return out
