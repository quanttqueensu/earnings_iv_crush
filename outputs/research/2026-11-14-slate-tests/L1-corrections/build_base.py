"""
build_base.py
L1 corrections: rebuild every event of the base panel through the closed hedged-event-hold
builder, check it reproduces the stored ``H`` exactly, and re-settle the recorded path under the
adopted netting (``HEDGED_NET``), early call assignment before ex-dividend dates, the paper book's
ex-date skip and financing. Writes ``base_corrected.parquet`` and ``build_base.log``.

Usage
-----
    python outputs/research/2026-11-14-slate-tests/L1-corrections/build_base.py
    python outputs/research/2026-11-14-slate-tests/L1-corrections/build_base.py --limit 200

The closed study module is imported, never edited: its ``hedged_short_straddle`` and
``stock_path`` names are wrapped in the imported copy so the exact inputs it would value are
recorded, and the package function is then called on those inputs with each correction.

2025-26 stock paths. ``confirm.py`` downloaded Yahoo bars without saving them and Yahoo is not
fetched again. The path is rebuilt from the cached adjusted closes
(``data/cache/yahoo_adj/adj_close.parquet``): the total return is the adjusted close's change,
exactly what ``confirm.py`` used, and the as-traded close is recovered backwards from the stored
settlement close, ``raw[t-1] = adj[t-1] raw[t] / adj[t] + D[t]`` with ``D`` the cash dividend
whose ex-date is ``t`` (``outputs/research/parity_spread/dividends.parquet``, ex-dates
2025-01-06 to 2026-06-26). An event counts as rebuilt only when the closed builder, fed this
path, reproduces the stored ``H`` to 1e-9 of m0; a missing in-hold dividend breaks that test.
"""

from __future__ import annotations

import argparse
import importlib.util
import os
import sys
import time
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from earnings_iv_crush.config import HEDGED, HEDGED_NET, HOLD_CORRECTIONS  # noqa: E402
from earnings_iv_crush.engine.stats import nyse_sessions  # noqa: E402
from earnings_iv_crush.research import hedged_hold as hh  # noqa: E402

HERE = Path(__file__).resolve().parent
BASE = ROOT / "outputs" / "research" / "2026-11-02-parity-leg-choice" / "events.parquet"
FEATURES = ROOT / "outputs" / "research" / "2026-10-20-hedged-hold" / "features.parquet"
CRSP = ROOT / "outputs" / "research" / "2026-10-20-hedged-hold" / "crsp_paths.parquet"
YADJ = ROOT / "data" / "cache" / "yahoo_adj" / "adj_close.parquet"
YDIV = ROOT / "outputs" / "research" / "parity_spread" / "dividends.parquet"
DFF = (
    ROOT / "outputs" / "research" / "2026-11-13-alpha-hunt" / "lane1-macro" / "dl" / "fred_DFF.csv"
)
HH_STUDY = ROOT / "research" / "timing" / "2026-11-02-hedged-event-hold" / "study.py"
PAIRWISE = ROOT / "research" / "selection" / "2026-11-07-pairwise-tercile-gates" / "study.py"
OUT = HERE / "base_corrected.parquet"

REPRO_TOL = {"crsp": 1e-9, "yahoo": 1e-5}  # m0; rebuilt path must give the stored H this close
# The Yahoo tolerance absorbs the rounding of a re-scaled adjusted series (observed gaps up to
# about 2e-6 on dividend payers, exactly zero on non-payers); a missing in-hold dividend moves H
# by about D times the hedge over m0, of order 1e-3, and fails it.
YDIV_FIRST, YDIV_LAST = pd.Timestamp("2025-01-06"), pd.Timestamp("2026-06-26")
CRSP_LAST = pd.Timestamp("2024-12-31")
YAHOO_END = pd.Timestamp("2026-12-31")  # confirm.py's override of the study's CRSP_END
FC = HOLD_CORRECTIONS


# ── imported closed modules ─────────────────────────────────────────────────


def _load(name: str, path: Path) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


class _Recorder:
    """Wraps the study's valuation and path calls to keep the inputs of the last event."""

    def __init__(self, st: Any) -> None:
        self.kw: dict | None = None
        self.g: pd.DataFrame | None = None
        self._value, self._path = st.hedged_short_straddle, st.stock_path
        st.hedged_short_straddle, st.stock_path = self.value, self.path

    def reset(self) -> None:
        self.kw, self.g = None, None

    def value(self, **kw: Any) -> hh.HedgedResult:
        if kw.get("hedge", True) and self.kw is None:
            self.kw = {k: v for k, v in kw.items() if k != "hedge"}
        return self._value(**kw)

    def path(self, *a: Any, **k: Any) -> tuple[str, pd.DataFrame | None]:
        st_, g = self._path(*a, **k)
        self.g = g
        return st_, g


# ── worker state ─────────────────────────────────────────────────────────────

_W: dict[str, Any] = {}


def _init_worker() -> None:
    st = _load("hedged_event_hold_study", HH_STUDY)
    pw = _load("pairwise_study", PAIRWISE)
    sys.modules["hh_study"] = _load("hh_study", HH_STUDY)  # pairwise's exit readers, unwrapped
    _W["st"], _W["pw"], _W["rec"] = st, pw, _Recorder(st)
    _W["crsp"] = st.load_crsp()
    y = pd.read_parquet(YADJ)
    y.index = pd.to_datetime(y.index).normalize()
    _W["yadj"] = y
    dv = pd.read_parquet(YDIV)
    dv["ex_date"] = pd.to_datetime(dv["ex_date"]).dt.normalize()
    _W["ydiv"] = {
        (t, d): float(x)
        for t, d, x in zip(dv["ticker"], dv["ex_date"], dv["dividend"], strict=True)
    }
    r = pd.read_csv(DFF, parse_dates=["observation_date"])
    r = r.set_index("observation_date")["DFF"].astype(float) / 100.0
    _W["dff"] = r.reindex(pd.date_range(r.index.min(), r.index.max(), freq="D")).ffill()


def _rate(d: pd.Timestamp) -> float:
    v = float(_W["dff"].get(pd.Timestamp(d).normalize(), np.nan))
    if not np.isfinite(v):
        raise ValueError(f"no DFF rate for {d}")
    return v


def _yahoo_path(ticker: str, start: pd.Timestamp, expiry: pd.Timestamp, settle: float) -> Any:
    """CRSP-shaped frame on the hold's sessions rebuilt from adjusted closes; None if absent."""
    if ticker not in _W["yadj"].columns:
        return None
    adj_all = _W["yadj"][ticker].dropna()
    ret_all = adj_all.pct_change()
    sess = nyse_sessions(start, expiry)
    adj = adj_all.reindex(sess)
    if len(sess) == 0 or adj.isna().any():
        return None
    a = adj.to_numpy(float)
    raw = np.empty_like(a)
    raw[-1] = settle
    for j in range(len(a) - 1, 0, -1):
        d = _W["ydiv"].get((ticker, sess[j]), 0.0)
        raw[j - 1] = a[j - 1] * raw[j] / a[j] + d
    hs = confirm_half_spread()
    return pd.DataFrame(
        {
            "prc": raw,
            "ret": ret_all.reindex(sess).to_numpy(float),
            "bid": raw * (1 - hs),
            "ask": raw * (1 + hs),
            "cfacpr": 1.0,
        },
        index=sess,
    )


def confirm_half_spread() -> float:
    """The 3 bp per-side Yahoo half-spread frozen in amendment 01 (confirm.py)."""
    return 3e-4


# ── dividends inside the hold ────────────────────────────────────────────────


def _crsp_divs(permno: float, lo: pd.Timestamp, hi: pd.Timestamp) -> list[tuple]:
    """(ex_date, D, cum close) recovered from CRSP total against price return in (lo, hi]."""
    g = _W["crsp"].get(int(permno)) if np.isfinite(permno) else None
    if g is None:
        return []
    w = g.loc[(g.index >= lo - pd.Timedelta(days=10)) & (g.index <= hi)]
    out = []
    prev = w["prc"].shift(1)
    cf_prev = w["cfacpr"].shift(1)
    for d, p, pp, r, cf, cfp in zip(
        w.index, w["prc"], prev, w["ret"], w["cfacpr"], cf_prev, strict=True
    ):
        if d <= lo or not (np.isfinite(pp) and np.isfinite(r)) or cf != cfp:
            continue
        div = (1 + r) * pp - p
        if div > FC.min_recovered_div:
            out.append((pd.Timestamp(d), float(div), float(pp)))
    return out


def _crsp_prior_divs(permno: float, before: pd.Timestamp, n: int = 4) -> list[float]:
    g = _W["crsp"].get(int(permno)) if np.isfinite(permno) else None
    if g is None:
        return []
    w = g.loc[(g.index < before) & (g.index >= before - pd.Timedelta(days=500))]
    div = (1 + w["ret"]) * w["prc"].shift(1) - w["prc"]
    div = div[(w["cfacpr"] == w["cfacpr"].shift(1)) & (div > FC.min_recovered_div)]
    return [float(x) for x in div.to_numpy()[-n:]]


def _yahoo_divs(ticker: str, lo: pd.Timestamp, hi: pd.Timestamp) -> list[tuple]:
    return [(d, x, np.nan) for (t, d), x in _W["ydiv"].items() if t == ticker and lo < d <= hi]


def _is_special(div: float, cum: float, prior: list[float]) -> bool:
    per_contract = div * FC.contract_multiplier
    big = np.isfinite(cum) and cum > 0 and div >= FC.occ_large_div_frac * cum
    irregular = bool(prior) and div > FC.special_div_ratio * float(np.median(prior))
    return bool(big or (per_contract >= FC.special_div_per_contract and irregular))


# ── one event ────────────────────────────────────────────────────────────────


def build_one(args: tuple[dict, dict]) -> dict:
    frow, brow = args
    st, rec, pw = _W["st"], _W["rec"], _W["pw"]
    key = {"ticker": brow["ticker"], "entry_date": pd.Timestamp(brow["entry_date"])}
    src = brow["src"]
    row = pd.Series(frow)
    entry, exp = pd.Timestamp(row["entry_date"]), pd.Timestamp(row["front_expiry"])
    t1 = pd.Timestamp(row["exit_date"])
    # residual value at the reaction session's 15:59 marks (the pairwise-gates definition); it
    # needs no stock path, so it is computed for every event, rebuilt or not
    k0 = float(row["front_strike"])
    m0_0 = st.MARGIN_SPOT_FRAC * float(row["front_fwd"]) + float(row["front_bid"])
    mk = pw._marks_one((row["ticker"], entry, t1, k0, exp, m0_0))
    key = {
        **key,
        "residual_value": mk.get("residual_value", np.nan),
        "rv_status": mk.get("mark_status"),
    }
    if src == "yahoo":
        st.CRSP_END = YAHOO_END
        path = _yahoo_path(row["ticker"], t1, exp, float(brow["settle"]))
        if path is None:
            return {**key, "h_status": "no_cached_yahoo_path"}
        crsp, row["permno"] = {0: path}, 0.0
    else:
        st.CRSP_END = CRSP_LAST
        crsp = _W["crsp"]
    rec.reset()
    b = st.build_event(row, crsp)
    if b.get("status") != "ok":
        return {**key, "h_status": f"rebuild_{b.get('status')}"}
    gap = abs(float(b["H"]) - float(brow["H"]))
    out: dict = {**key, "repro_gap": gap}
    if not gap <= REPRO_TOL[src]:
        return {**out, "h_status": "not_reproduced"}

    m0, s0, k = float(b["m0"]), float(b["s0"]), float(b["strike"])
    g = rec.g
    assert g is not None
    dates = g.index
    settle_day = pd.Timestamp(dates[-1])

    # dividends with an ex-date in (entry, expiry] and the live rule's [entry, expiry]
    if src == "yahoo":
        divs = _yahoo_divs(row["ticker"], entry - pd.Timedelta(days=1), exp)
        covered = YDIV_FIRST <= entry and exp <= YDIV_LAST
        closes_by_day = dict(zip(dates, g["prc"], strict=True))
        divs = [
            (d, x, closes_by_day.get(dates[max(0, int(np.searchsorted(dates, d)) - 1)], np.nan))
            for d, x, _ in divs
        ]
    else:
        divs = _crsp_divs(float(row["permno"]), entry - pd.Timedelta(days=1), exp)
        covered = True
    in_hold = [x for x in divs if x[0] > entry]
    on_entry = any(x[0] == entry for x in divs)
    special = False
    for d, x, cum in in_hold:
        prior = (
            _crsp_prior_divs(float(row["permno"]), d)
            if src == "crsp"
            else [v for (t, dd), v in _W["ydiv"].items() if t == row["ticker"] and dd < d][-4:]
        )
        special = special or _is_special(x, cum, prior)
    exdiv_known = covered or bool(divs)
    out.update(
        {
            "spot_src": "crsp" if src == "crsp" else "yahoo_adj_rebuilt",
            "exdiv_in_hold": bool(in_hold) if exdiv_known else np.nan,
            "exdiv_on_or_before_reaction": bool(any(x[0] <= t1 for x in in_hold)),
            "exdiv_on_entry": on_entry,
            "div_in_hold": float(sum(x[1] for x in in_hold)),
            "special_div": special,
            "m0": m0,
            "s0": s0,
            "strike": k,
            "n_hedge": int(b["n_hedge"]),
            "settle": float(b["settle"]),
        }
    )
    fee = 2.0 * HEDGED.fee_per_contract_leg / 100.0
    prem_days = float((settle_day - entry).days)
    credit = max(_rate(entry) - FC.cash_credit_spread_bps / 1e4, 0.0)
    prem_int = s0 * credit * prem_days / FC.day_basis

    if b["n_hedge"] == 0 or rec.kw is None:
        # settles on the reaction session: no hedge, so netting and early assignment are moot
        h = float(b["H"])
        out.update(
            H_rebuilt=h,
            H_net=h,
            H_exdiv=h,
            H_fin=h + prem_int / m0,
            H_corr=h + prem_int / m0,
            H_corr_put=h + prem_int / m0,
            call_assigned=False,
            put_assigned_put_variant=False,
            call_assigned_exdiv=False,
            c_premium=s0 / m0,
            c_settlement=-float(b["intrinsic"]) / m0,
            c_hedge=0.0,
            c_equity_cost=0.0,
            c_fees=-fee / m0,
            c_disposal=-float(b["disposal"]) / m0,
            c_financing=prem_int / m0,
        )
    else:
        kw = rec.kw
        n = len(kw["closes"])
        # dividend paid into rets[i] has its ex-date at session i + 1
        dv = np.zeros(n)
        for d, x, _ in in_hold:
            j = int(np.searchsorted(dates, d))
            if 1 <= j <= n and dates[j] == d:
                dv[j - 1] += x
        taus_ex = np.array([hh.year_frac(dates[i + 1], exp) for i in range(n)])
        rates = np.array([_rate(dates[i]) for i in range(n)])
        days = np.array([float((dates[i + 1] - dates[i]).days) for i in range(n)])
        fin = hh.HoldFinancing(
            rates=rates, days=days, premium_rate=_rate(entry), premium_days=prem_days, cfg=FC
        )
        sig = kw["sigmas"]
        r_old = hh.hedged_short_straddle(**kw, cfg=HEDGED)
        if abs(r_old.net_pnl / m0 - float(brow["H"])) > REPRO_TOL[src]:
            return {**out, "h_status": "package_not_reproduced"}
        r_net = hh.hedged_short_straddle(**kw, cfg=HEDGED_NET)
        no_ex = special  # OCC adjusts a special dividend by strike; no early exercise motive
        jc = (
            -1
            if no_ex
            else hh.optimal_call_exercise(
                closes=kw["closes"], strike=k, dividends=dv, taus_ex=taus_ex, sigmas=sig
            )
        )
        r_ex = hh.hedged_short_straddle(
            **kw, cfg=HEDGED_NET, call_assigned_at=jc if jc >= 0 else None
        )
        r_fin = hh.hedged_short_straddle(**kw, cfg=HEDGED_NET, financing=fin)
        jc_r = (
            -1
            if no_ex
            else hh.optimal_call_exercise(
                closes=kw["closes"],
                strike=k,
                dividends=dv,
                taus_ex=taus_ex,
                sigmas=sig,
                rates=rates,
            )
        )
        jp = hh.optimal_put_exercise(
            closes=kw["closes"], strike=k, taus=kw["taus"], sigmas=sig, rates=rates
        )
        r_c = hh.hedged_short_straddle(
            **kw,
            cfg=HEDGED_NET,
            financing=fin,
            call_assigned_at=jc_r if jc_r >= 0 else None,
            put_assigned_at=jp if jp >= 0 else None,
        )
        r_np = hh.hedged_short_straddle(
            **kw, cfg=HEDGED_NET, financing=fin, call_assigned_at=jc_r if jc_r >= 0 else None
        )
        # the declared headline leaves out early put exercise: its rule overstates exercise
        comp = {
            "c_premium": s0 / m0,
            "c_settlement": -r_np.settlement / m0,
            "c_hedge": r_np.hedge_pnl / m0,
            "c_equity_cost": -r_np.equity_cost / m0,
            "c_fees": -r_np.fees / m0,
            "c_disposal": -r_np.disposal / m0,
            "c_financing": r_np.financing / m0,
        }
        if abs(sum(comp.values()) - r_np.net_pnl / m0) > 1e-12:
            raise AssertionError(f"components do not sum for {key}")
        out.update(
            H_rebuilt=r_old.net_pnl / m0,
            H_net=r_net.net_pnl / m0,
            H_exdiv=r_ex.net_pnl / m0,
            H_fin=r_fin.net_pnl / m0,
            H_corr=r_np.net_pnl / m0,
            H_corr_put=r_c.net_pnl / m0,
            call_assigned=jc_r >= 0,
            put_assigned_put_variant=jp >= 0,
            call_assigned_exdiv=jc >= 0,
            **comp,
        )
    out["h_status"] = "ok"
    return out


# ── driver ───────────────────────────────────────────────────────────────────


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--workers", type=int, default=max(1, (os.cpu_count() or 2) - 2))
    a = ap.parse_args(argv)
    base = pd.read_parquet(BASE)
    f = pd.read_parquet(FEATURES)
    for c in ("entry_date", "exit_date", "front_expiry"):
        f[c] = pd.to_datetime(f[c])
    base["entry_date"] = pd.to_datetime(base["entry_date"])
    f = f.drop_duplicates(["ticker", "entry_date"])
    m = base.merge(
        f, on=["ticker", "entry_date"], how="left", suffixes=("_b", ""), validate="one_to_one"
    )
    if m["front_fwd"].isna().any():
        raise ValueError(f"{int(m['front_fwd'].isna().sum())} base events lack features")
    if not (m["exit_date"] == pd.to_datetime(m["exit_date_b"])).all():
        raise ValueError("base and feature exit dates disagree")
    if a.limit:
        m = m.groupby("src", group_keys=False).head(a.limit)
    fcols = list(f.columns)
    jobs = [
        (
            {c: r[c] for c in fcols},
            {c: r[c] for c in ("ticker", "entry_date", "src", "H", "settle")},
        )
        for _, r in m.iterrows()
    ]
    print(f"base events: {len(base)}; jobs: {len(jobs)}; workers {a.workers}", flush=True)
    t0 = time.time()
    with ProcessPoolExecutor(max_workers=a.workers, initializer=_init_worker) as ex:
        res = list(ex.map(build_one, jobs, chunksize=25))
    print(f"built in {time.time() - t0:.0f}s", flush=True)
    d = pd.DataFrame(res)
    keep = ["ticker", "entry_date", "exit_date", "expiry", "src", "year", "H", "B", "permno"]
    d = (
        m[keep]
        .reset_index(drop=True)
        .merge(
            d.drop(columns=[c for c in ("m0", "s0", "strike", "settle") if c in d]),
            on=["ticker", "entry_date"],
            how="left",
            validate="one_to_one",
        )
    )
    d = d.merge(
        m[["ticker", "entry_date", "m0", "strike", "front_fwd"]],
        on=["ticker", "entry_date"],
        how="left",
        validate="one_to_one",
    )
    d["lnFK"] = np.log(d["front_fwd"] / d["strike"])
    d["spot_src"] = d["spot_src"].fillna("yahoo_not_rebuilt")
    d["H_skip"] = np.where(
        d["exdiv_in_hold"].astype("boolean").fillna(True) | d["exdiv_on_entry"].fillna(False),
        np.nan,
        d["H_net"],
    )
    d["block"] = pd.cut(
        d["year"], [2012, 2018, 2024, 2026], labels=["2013-18", "2019-24", "2025-26"]
    ).astype(str)
    print("funnel (h_status):")
    for k_, v in Counter(d["h_status"]).most_common():
        print(f"  {k_:28s} {v}")
    print("funnel by source:")
    print(d.groupby(["src", "h_status"]).size().to_string())
    print(f"max reproduction gap on ok rows: {d.loc[d['h_status'] == 'ok', 'repro_gap'].max():.2e}")
    print("residual value marks:", dict(Counter(d["rv_status"].fillna("not_built"))))
    if not a.limit:
        d.to_parquet(OUT)
        print(f"wrote {OUT} ({len(d)} rows)")


if __name__ == "__main__":
    main()
