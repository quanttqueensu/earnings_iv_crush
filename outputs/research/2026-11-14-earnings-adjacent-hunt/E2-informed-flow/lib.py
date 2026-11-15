"""
lib.py
Lane E2 (informed flow): event lists, quote-rule signed flow on the event's at-the-money option
pair, parity forwards from the cached 15:59 chains, CRSP lookups, and the scoring helpers.

Signals use only records strictly before the decision time on the entry session. Outcome helpers
(forwards on the reaction session, CRSP closes and opens) are separate functions so that a
feature build never touches an outcome.

References
----------
Easley, D., O'Hara, M. and Srinivas, P. S. (1998). Option volume and stock prices: evidence on
    where informed traders trade. Journal of Finance 53(2), 431-465.
Lee, C. M. C. and Ready, M. J. (1991). Inferring trade direction from intraday data. Journal of
    Finance 46(2), 733-746.
Pan, J. and Poteshman, A. M. (2006). The information in option volume for future stock prices.
    Review of Financial Studies 19(3), 871-908.
"""

from __future__ import annotations

import csv
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
sys.path.insert(0, str(ROOT))

from earnings_iv_crush.research.protocol import date_clustered_ci  # noqa: E402

TZ = "America/New_York"
FLOW = ROOT / "data" / "cache" / "flow"
CHAINS = ROOT / "data" / "cache" / "backfill_chains"
HH_EVENTS = ROOT / "outputs" / "research" / "2026-11-02-hedged-event-hold" / "events.parquet"
HH_CONFIRM = (
    ROOT / "outputs" / "research" / "2026-11-02-hedged-event-hold" / "events_confirm_2025_26.parquet"
)
PANEL = ROOT / "outputs" / "research" / "reverse_alpha" / "panel.parquet"
OOS_LEDGER = ROOT / "outputs" / "research" / "oos_2026_ledger.csv"
FEATURES = ROOT / "outputs" / "research" / "2026-10-20-hedged-hold" / "features.parquet"
CRSP = ROOT / "outputs" / "research" / "2026-10-20-hedged-hold" / "crsp_paths.parquet"
TRIALS = HERE / "trials.csv"

# ── declared constants (diagnosis.log entry 1) ──────────────────────────────
DISC = (pd.Timestamp("2023-03-28"), pd.Timestamp("2024-12-31"))
HELD = (pd.Timestamp("2025-01-01"), pd.Timestamp("2026-12-31"))
WIN_FROM, WIN_TO = "15:00", "15:50"  # signal window [from, to) on the entry session
MIN_SIGNED = 10  # the F2 floor on signed contracts
N_BINS, MIN_PRIOR = 5, 200  # causal quintiles, standing burn-in
EXTRA_BPS = 1.0  # per side on top of the stock half-spread (brief rule 5)
DEFAULT_HALF_BPS = 3.0  # ShadowConfig.equity_half_spread_bps, 90th pct of CRSP 2024 halves
N_DRAW, SEED = 5000, 0

FIELDS = [
    "trial_id",
    "hypothesis",
    "block",
    "n",
    "effect",
    "ci_low",
    "ci_high",
    "t",
    "sharpe",
    "null_dir_pct",
    "null_matched_pct",
    "basis",
    "verdict",
    "label",
]


# ── events ──────────────────────────────────────────────────────────────────


def _files(cache: str, kind: str) -> pd.DataFrame:
    rows = []
    for p in sorted((FLOW / cache).glob(f"*_{kind}.parquet")):
        stem = p.name[: -len(f"_{kind}.parquet")]
        tick, day = stem.rsplit("_", 1)
        rows.append({"ticker": tick, "entry_date": pd.Timestamp(day), "path": str(p), "cache": cache})
    return pd.DataFrame(rows)


def events(block: str) -> pd.DataFrame:
    """Flow events of a block with their reaction session; prints the funnel."""
    if block == "discovery":
        br = _files("broad_2023_2024", "entry")
        mc = _files("megacap_2023_2024", "pre")
        hh = pd.read_parquet(HH_EVENTS, columns=["ticker", "entry_date", "exit_date"])
        pn = pd.read_parquet(PANEL, columns=["ticker", "entry_date", "exit_date", "block"])
        pn = pn[pn["block"] == "discovery_2019_2024"].drop(columns="block")
        ref = pd.concat([pn, hh], ignore_index=True)
        ref["entry_date"] = pd.to_datetime(ref["entry_date"])
        ref["exit_date"] = pd.to_datetime(ref["exit_date"])
        ref = ref.drop_duplicates(["ticker", "entry_date"])
        both = pd.concat([mc, br], ignore_index=True)
        n0 = len(both)
        both = both.drop_duplicates(["ticker", "entry_date"], keep="first")  # pre file kept
        print(f"funnel[discovery]: files {n0} (megacap {len(mc)}, broad {len(br)}), "
              f"after de-duplication {len(both)}")
        lo, hi = DISC
    elif block == "heldout":
        both = _files("broad_2025_2026", "pre")
        ref = pd.read_csv(OOS_LEDGER, usecols=["ticker", "entry_date", "exit_date"])
        ref["entry_date"] = pd.to_datetime(ref["entry_date"])
        ref["exit_date"] = pd.to_datetime(ref["exit_date"])
        ref = ref.drop_duplicates(["ticker", "entry_date"])
        print(f"funnel[heldout]: files {len(both)}")
        lo, hi = HELD
    else:
        raise ValueError(block)
    d = both.merge(ref, on=["ticker", "entry_date"], how="left")
    miss = int(d["exit_date"].isna().sum())
    if miss:
        print(f"  funnel: {miss} files with no reaction session in the event lists (dropped)")
    d = d.dropna(subset=["exit_date"])
    d = d[(d["entry_date"] >= lo) & (d["entry_date"] <= hi)].reset_index(drop=True)
    print(f"  funnel: {len(d)} events inside {lo.date()}..{hi.date()}")
    if d.empty:
        raise SystemExit("no events in block")
    return d


# ── flow signal (entry session, strictly before the decision time) ──────────


def _occ(sym: str) -> tuple[str, pd.Timestamp, float]:
    body = sym.replace(" ", "")[-15:]
    return body[6], pd.Timestamp(pd.to_datetime(body[:6], format="%y%m%d")), int(body[7:]) / 1000.0


def _frame(path: str) -> pd.DataFrame:
    cols = ["action", "price", "size", "bid_px_00", "ask_px_00", "symbol"]
    df = pd.read_parquet(path, columns=cols)
    idx = pd.DatetimeIndex(df.index)
    idx = idx.tz_localize("UTC") if idx.tz is None else idx
    df = df.assign(t=idx.tz_convert(TZ)).reset_index(drop=True)
    df["symbol"] = df["symbol"].astype(str)
    return df


def _at(day: pd.Timestamp, hm: str) -> pd.Timestamp:
    h, m = map(int, hm.split(":"))
    return (pd.Timestamp(day).normalize() + pd.Timedelta(hours=h, minutes=m)).tz_localize(TZ)


def _last_mid(leg: pd.DataFrame, when: pd.Timestamp) -> float:
    q = leg[(leg["t"] < when) & (leg["bid_px_00"] > 0) & (leg["ask_px_00"] > leg["bid_px_00"])]
    if q.empty:
        return float("nan")
    r = q.iloc[-1]
    return float((r["bid_px_00"] + r["ask_px_00"]) / 2)


def _signed(leg: pd.DataFrame) -> pd.DataFrame:
    """Trades of one instrument with +1/-1/0 quote-rule sign against the prior two-sided mid."""
    leg = leg.sort_values("t", kind="stable")
    q = (leg["action"] != "T") & (leg["bid_px_00"] > 0) & (leg["ask_px_00"] > leg["bid_px_00"])
    mid = ((leg["bid_px_00"] + leg["ask_px_00"]) / 2).where(q)
    prior = mid.ffill().shift(1)  # last two-sided quote strictly before this record
    tr = leg[leg["action"] == "T"].assign(mid_prior=prior[leg["action"] == "T"])
    s = np.sign(tr["price"] - tr["mid_prior"]).fillna(0.0)
    return tr.assign(sign=s)


def _s_stat(tr: pd.DataFrame, weight: str = "size") -> tuple[float, float]:
    w = tr[weight].astype(float)
    call = tr["right"] == "C"
    buy, sell = tr["sign"] > 0, tr["sign"] < 0
    cb, cs = w[call & buy].sum(), w[call & sell].sum()
    pb, ps = w[~call & buy].sum(), w[~call & sell].sum()
    tot = cb + cs + pb + ps
    return ((cb - cs - pb + ps) / tot if tot > 0 else float("nan")), float(tot)


def flow_features(path: str, entry_date: pd.Timestamp) -> dict:
    """Signals and diagnostics from one flow file; nothing at or after 15:50 enters a signal."""
    df = _frame(path)
    syms = df["symbol"].unique()
    if len(syms) != 2:
        return {"status": f"symbols_{len(syms)}"}
    meta = {s: _occ(s) for s in syms}
    rights = {m[0] for m in meta.values()}
    if rights != {"C", "P"}:
        return {"status": "not_a_pair"}
    strikes = {m[2] for m in meta.values()}
    expiries = {m[1] for m in meta.values()}
    if len(strikes) != 1 or len(expiries) != 1:
        return {"status": "pair_mismatch"}
    df["right"] = df["symbol"].map(lambda s: meta[s][0])
    k, exp = strikes.pop(), expiries.pop()
    t0, t1 = _at(entry_date, WIN_FROM), _at(entry_date, WIN_TO)
    trs = pd.concat([_signed(g) for _, g in df.groupby("symbol")], ignore_index=True)
    trs = trs.assign(prem=trs["price"] * trs["size"])
    w = trs[(trs["t"] >= t0) & (trs["t"] < t1)]
    s_main, n_main = _s_stat(w)
    s_prem, _ = _s_stat(w, "prem")
    big = w[w["size"] >= 10]
    s_big, n_big = _s_stat(big)
    day0 = pd.Timestamp(entry_date).normalize().tz_localize(TZ)
    pre = trs[trs["t"] < t1]  # the whole file before the decision time (pre files: 2+ sessions)
    s_long, n_long = _s_stat(pre)
    s_day, n_day = _s_stat(trs[(trs["t"] >= day0) & (trs["t"] < t1)])
    legs = {r: df[df["right"] == r] for r in "CP"}

    def fwd(when: pd.Timestamp) -> float:
        c, p = _last_mid(legs["C"], when), _last_mid(legs["P"], when)
        return k + c - p if np.isfinite(c) and np.isfinite(p) else float("nan")

    f1500, f1550 = fwd(t0), fwd(t1)
    f1559 = fwd(_at(entry_date, "15:59") + pd.Timedelta(seconds=1))
    call, buy, sell = w["right"] == "C", w["sign"] > 0, w["sign"] < 0
    sz = w["size"].astype(float)
    return {
        "cb": float(sz[call & buy].sum()),
        "cs": float(sz[call & sell].sum()),
        "pb": float(sz[~call & buy].sum()),
        "ps": float(sz[~call & sell].sum()),
        "c_mid_1550": _last_mid(legs["C"], t1),
        "p_mid_1550": _last_mid(legs["P"], t1),
        "status": "ok",
        "strike": k,
        "expiry": exp,
        "S": s_main,
        "n_signed": n_main,
        "unsigned_share": float((w["sign"] == 0).mean()) if len(w) else float("nan"),
        "S_prem": s_prem,
        "S_big": s_big,
        "n_big": n_big,
        "S_long": s_long,
        "n_long": n_long,
        "S_day": s_day,
        "n_day": n_day,
        "first_ts": df["t"].min(),
        "f_flow_1500": f1500,
        "f_flow_1550": f1550,
        "f_flow_1559": f1559,
    }


def add_delta_signal(f: pd.DataFrame) -> pd.DataFrame:
    """S_delta (diagnosis.log entry 5): signed contracts weighted by Black forward deltas at 15:50.

    sigma is the 15:50 straddle mid's implied vol on the 15:50 parity forward; T runs from
    15:50 on the entry session to 16:00 on expiry, ACT/365. Events without a bracketed vol get
    NaN (counted), never a default.
    """
    from scipy.stats import norm

    from earnings_iv_crush.research.hedged_hold import straddle_iv

    f = f.copy()
    t = ((pd.to_datetime(f["expiry"]) + pd.Timedelta(hours=16))
         - (pd.to_datetime(f["entry_date"]) + pd.Timedelta(hours=15, minutes=50))).dt.total_seconds()
    f["T"] = t / (365 * 86400)
    prem = f["c_mid_1550"] + f["p_mid_1550"]
    f["sigma_1550"] = [straddle_iv(p, F, k, tt) if np.isfinite(p) and np.isfinite(F) else np.nan
                       for p, F, k, tt in zip(prem, f["f_flow_1550"], f["strike"], f["T"],
                                              strict=True)]
    srt = f["sigma_1550"] * np.sqrt(f["T"])
    d1 = (np.log(f["f_flow_1550"] / f["strike"]) + 0.5 * srt**2) / srt
    dc = pd.Series(norm.cdf(d1), index=f.index)
    dp = 1.0 - dc  # |put delta| on the forward
    num = dc * (f["cb"] - f["cs"]) + dp * (f["ps"] - f["pb"])
    den = dc * (f["cb"] + f["cs"]) + dp * (f["pb"] + f["ps"])
    f["delta_c"] = dc
    f["S_delta"] = (num / den).where(den > 0)
    f["moneyness"] = f["strike"] / f["f_flow_1550"] - 1
    n_nan = int((f["n_signed"] >= MIN_SIGNED).sum() - f.loc[f["n_signed"] >= MIN_SIGNED,
                                                            "S_delta"].notna().sum())
    print(f"add_delta_signal: {n_nan} signalled events without a bracketed 15:50 vol (no S_delta)")
    return f


# ── parity forwards from the cached 15:59 chains ────────────────────────────


def chain_fwd(ticker: str, day: pd.Timestamp, expiry: pd.Timestamp) -> tuple[float, float, str]:
    """Parity forward at 15:59 for ``expiry`` at the strike minimising |C - P| (two-sided legs).

    Returns (forward, strike used, status). Mirrors the hedged-event-hold study's exit_fwd rule.
    """
    p = CHAINS / f"{ticker}_{pd.Timestamp(day).date()}.parquet"
    if not p.exists():
        return float("nan"), float("nan"), "no_chain"
    d = pd.read_parquet(p, columns=["symbol", "bid_px_00", "ask_px_00"]).reset_index()
    body = d["symbol"].astype(str).str.replace(" ", "", regex=False).str[-15:]
    d["right"] = body.str[6]
    d["strike"] = pd.to_numeric(body.str[7:], errors="coerce") / 1000.0
    d["expiry"] = pd.to_datetime(body.str[:6], format="%y%m%d", errors="coerce")
    d = d[(d["expiry"] == pd.Timestamp(expiry)) & (d["bid_px_00"] > 0) & (d["ask_px_00"] > 0)]
    d = d[d["ask_px_00"] >= d["bid_px_00"]]
    if d.empty:
        return float("nan"), float("nan"), "no_expiry_quotes"
    d = d.sort_values("ts_recv").groupby(["strike", "right"], as_index=False).last()
    d["mid"] = (d["bid_px_00"] + d["ask_px_00"]) / 2
    w = d.pivot(index="strike", columns="right", values="mid").dropna()
    if w.empty or not {"C", "P"} <= set(w.columns):
        return float("nan"), float("nan"), "no_pair"
    k = float((w["C"] - w["P"]).abs().idxmin())
    return float(k + w.loc[k, "C"] - w.loc[k, "P"]), k, "ok"


def outcome_expiry(ticker: str, entry: pd.Timestamp, exit_: pd.Timestamp,
                   sold: pd.Timestamp) -> pd.Timestamp | None:
    """Sold expiry if it expires after the reaction session, else the next listed one."""
    if pd.Timestamp(sold) > pd.Timestamp(exit_):
        return pd.Timestamp(sold)
    p = CHAINS / f"{ticker}_{pd.Timestamp(entry).date()}.parquet"
    if not p.exists():
        return None
    d = pd.read_parquet(p, columns=["symbol"])
    body = d["symbol"].astype(str).str.replace(" ", "", regex=False).str[-15:]
    e = pd.to_datetime(body.str[:6], format="%y%m%d", errors="coerce").dropna().unique()
    later = sorted(x for x in e if x > pd.Timestamp(exit_))
    return pd.Timestamp(later[0]) if later else None


def chain_strikes(ticker: str, day: pd.Timestamp, expiry: pd.Timestamp) -> np.ndarray:
    p = CHAINS / f"{ticker}_{pd.Timestamp(day).date()}.parquet"
    if not p.exists():
        return np.array([])
    d = pd.read_parquet(p, columns=["symbol"])
    body = d["symbol"].astype(str).str.replace(" ", "", regex=False).str[-15:]
    e = pd.to_datetime(body.str[:6], format="%y%m%d", errors="coerce")
    k = pd.to_numeric(body.str[7:], errors="coerce") / 1000.0
    return np.unique(k[e == pd.Timestamp(expiry)].dropna().to_numpy())


# ── CRSP ────────────────────────────────────────────────────────────────────


def permno_map() -> dict[str, int]:
    f = pd.read_parquet(FEATURES, columns=["ticker", "entry_date", "permno"]).dropna()
    f = f.sort_values("entry_date")
    return {t: int(g["permno"].iloc[-1]) for t, g in f.groupby("ticker")}


def load_crsp() -> pd.DataFrame:
    c = pd.read_parquet(CRSP)
    for col in ("prc", "bid", "ask"):
        c[col] = pd.to_numeric(c[col], errors="coerce").astype(float)
    c["prc"] = c["prc"].abs()
    c["date"] = pd.to_datetime(c["date"])
    c["half"] = (c["ask"] - c["bid"]) / (c["ask"] + c["bid"])
    c.loc[(c["bid"] <= 0) | (c["ask"] <= c["bid"]), "half"] = np.nan
    return c.set_index(["permno", "date"]).sort_index()


# ── scoring helpers ─────────────────────────────────────────────────────────


def null_random_direction(net_abs_signed: np.ndarray, gross: np.ndarray, cost: np.ndarray,
                          observed: float) -> float:
    """Percentile of the observed mean among same-event, random-sign books."""
    rng = np.random.default_rng(SEED)
    n = gross.size
    draws = np.empty(N_DRAW)
    for i in range(N_DRAW):
        s = rng.choice([-1.0, 1.0], size=n)
        draws[i] = float(np.mean(s * gross - cost))
    return float(100.0 * (draws < observed).mean())


def null_matched(pool_gross: np.ndarray, pool_cost: np.ndarray, n_long: int, n_short: int,
                 observed: float) -> float:
    """Percentile of the observed mean among random books with the same long and short counts."""
    rng = np.random.default_rng(SEED)
    m = pool_gross.size
    draws = np.empty(N_DRAW)
    for i in range(N_DRAW):
        idx = rng.choice(m, size=n_long + n_short, replace=False)
        s = np.r_[np.ones(n_long), -np.ones(n_short)]
        draws[i] = float(np.mean(s * pool_gross[idx] - pool_cost[idx]))
    return float(100.0 * (draws < observed).mean())


def mean_ci(x: np.ndarray, dates: pd.Series):
    return date_clustered_ci(x, dates, stat=np.mean, n_boot=N_DRAW, seed=SEED)


def sharpe_ci(x: np.ndarray, dates: pd.Series):
    return date_clustered_ci(x, dates, n_boot=N_DRAW, seed=SEED)


def log_trial(row: dict) -> None:
    new = not TRIALS.exists()
    with TRIALS.open("a", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=FIELDS)
        if new:
            w.writeheader()
        w.writerow({k: row.get(k, "") for k in FIELDS})
