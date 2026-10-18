"""
research_section21_peer.py
Peer-informed selection scored on repricing, not size: the frozen section 2.1 test.

Implements ``research/selection/preregs/section21_peer_prereg.md`` exactly. Three trials share one outcome
(the moneyness-adjusted residual value ``R_adj``) and one staged sequence:

    A_peer_relative_jump_kmeans   log(J_i / median J of eligible k-means peers), sell high
    B_peer_realisation_kmeans     -median(realised / implied) of eligible k-means peers
    B_peer_realisation_sic2       the same with two-digit CRSP SIC peers (comparator)

Stages run in order and a failed candidate stops: discovery (2019-2024 megacap) for all
three; validation (2013-2018 megacap) only for a candidate passing every discovery
criterion; confirmation (2025-2026 ledger, megacap subset primary, all names secondary) only
for a candidate passing validation. The pre-registration hash is checked before anything is
computed, and the run refuses to start if it differs.

Usage:
    python research/selection/research_section21_peer.py
    python research/selection/research_section21_peer.py --out outputs/research/section21_peer

References
----------
Arthur, D. and Vassilvitskii, S. (2007). k-means++: The Advantages of Careful Seeding.
*Proceedings of the 18th ACM-SIAM Symposium on Discrete Algorithms*, 1027-1035.
Dubinsky, A., Johannes, M., Kaeck, A. and Seeger, N. J. (2019). Option Pricing of Earnings
Announcement Risks. *Review of Financial Studies* 32(2), 646-687.
Frankel, R., Godigbe, B. G. and Rabier, M. (2025). Information Spillovers at Earnings
Announcements. *Journal of Accounting Research* 63(1), 319-362.
Hann, R. N., Kim, H. and Zheng, Y. (2019). Intra-industry Information Transfers: Evidence
from Changes in Implied Volatility around Earnings Announcements. *Review of Accounting
Studies* 24, 927-971.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

import numpy as np
import numpy.typing as npt
import pandas as pd
from scipy.stats import norm, spearmanr

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from earnings_iv_crush.engine.event_study import cluster_bootstrap_ci  # noqa: E402
from earnings_iv_crush.engine.stats import deflated_sharpe_ratio  # noqa: E402

# ── frozen inputs ────────────────────────────────────────────────────────────

PREREG = Path("research/selection/preregs/section21_peer_prereg.md")
PREREG_JSON = Path("outputs/research/prereg_section21.json")
PREREG_SHA256 = "04c3a43b7bada0c9955404b337b281a58ed1c6203478e22073f3fd5a84b6b764"
PANEL = Path("outputs/research/reverse_alpha/panel.parquet")
LEDGER = Path("outputs/research/oos_2026_ledger.csv")
EVENTS_2025 = Path("outputs/research/events_broad_oos_2025.parquet")
PERF = Path("outputs/research/performance_panel.csv")
OUT = Path("outputs/research/section21_peer")

DISCOVERY, VALIDATION = "discovery_2019_2024", "holdout_2013_2018"
TRIALS = ("A_peer_relative_jump_kmeans", "B_peer_realisation_kmeans", "B_peer_realisation_sic2")

ENTRY_HALF, EXIT_HALF = 0.012714, 0.030182  # measured 15:59 basis, fraction of mark per side
PREMIUM_ROUND_TRIP = 0.116  # second cost arm: round trip as a fraction of premium
BACK_TENOR_FALLBACK = 21 / 365  # prereg: t_b = t_f + 21/365 where the back expiry is absent
WINDOW_DAYS = 252  # trading days of returns per clustering window
MIN_VALID_RETURNS = 200  # names with fewer valid returns sit out that season's clustering
NAMES_PER_CLUSTER = 6  # k = round(N_names / 6)
KMEANS_N_INIT = 50
Q = 0.80
MIN_HIST = 25
N_BOOT = 5000
SEED = 0
SPEARMAN_MIN = 0.60
PREMIUM_SHARE_MAX = 0.5
CAUSAL_RATIO_MIN = 0.5
SPLICE_TOL = 1e-4  # 1 bp median absolute daily-return disagreement, CRSP vs yfinance
CRSP_END = pd.Timestamp("2024-12-31")
RETURNS_START = pd.Timestamp("2011-06-01")  # covers the 252-day window before 2013 seasons
DSR_TRIALS = 1489  # prereg trial accounting
LEDGER_TRIALS_NOW = 1503  # programme ledger as it stands, reported alongside

SEASON_STARTS = ((1, 10), (4, 10), (7, 10), (10, 10))


# ── pre-registration guard ───────────────────────────────────────────────────


def check_prereg(path: Path = PREREG, expected: str = PREREG_SHA256) -> str:
    """Refuse to run unless the pre-registration file hashes to the frozen value."""
    if not path.exists():
        raise SystemExit(f"pre-registration {path} not found - refusing to score")
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    recorded = json.loads(PREREG_JSON.read_text())["prereg_sha256"]
    if digest != expected or recorded != expected:
        raise SystemExit(
            f"pre-registration hash mismatch: file {digest}, recorded {recorded}, "
            f"frozen {expected} - refusing to score"
        )
    print(f"  prereg hash verified: {digest}")
    return digest


# ── pure building blocks (tested offline) ────────────────────────────────────


def season_start(d: pd.Timestamp) -> pd.Timestamp:
    """First day of the reporting season containing ``d``.

    Windows: 10 Jan to 9 Apr, 10 Apr to 9 Jul, 10 Jul to 9 Oct, 10 Oct to 9 Jan.
    """
    d = pd.Timestamp(d).normalize()
    starts = [pd.Timestamp(d.year, m, day) for m, day in SEASON_STARTS]
    past = [s for s in starts if s <= d]
    return past[-1] if past else pd.Timestamp(d.year - 1, 10, 10)


def priced_jump_var(
    f: npt.ArrayLike, b: npt.ArrayLike, t_f: npt.ArrayLike, t_b: npt.ArrayLike
) -> np.ndarray:
    """Priced announcement variance ``E = max(f^2 - b^2, 0) * t_f * t_b / (t_b - t_f)``."""
    fa, ba = np.asarray(f, dtype=float), np.asarray(b, dtype=float)
    tf, tb = np.asarray(t_f, dtype=float), np.asarray(t_b, dtype=float)
    with np.errstate(invalid="ignore", divide="ignore"):
        e = np.maximum(fa**2 - ba**2, 0.0) * tf * tb / (tb - tf)
    return np.where(tb > tf, e, np.nan)


def eligible_peer_mask(
    peer_ticker: np.ndarray,
    peer_season: np.ndarray,
    peer_exit: np.ndarray,
    ticker: str,
    season: pd.Timestamp,
    entry: pd.Timestamp,
    cluster_mates: set[str],
) -> np.ndarray:
    """Peers in the event's season and cluster, other than itself, exited by its entry."""
    in_cluster = np.isin(peer_ticker, list(cluster_mates - {ticker}))
    return in_cluster & (peer_season == np.datetime64(season)) & (peer_exit <= np.datetime64(entry))


def causal_quantile_rule(
    values: np.ndarray, dates: np.ndarray, q: float = Q, min_hist: int = MIN_HIST
) -> np.ndarray:
    """Take event i when its value is at or above the q-quantile of strictly earlier values."""
    values = np.asarray(values, dtype=float)
    dates = np.asarray(dates)
    out = np.zeros(len(values), dtype=bool)
    for i in range(len(values)):
        if np.isnan(values[i]):
            continue
        prior = values[(dates < dates[i]) & ~np.isnan(values)]
        if prior.size >= min_hist and values[i] >= np.quantile(prior, q):
            out[i] = True
    return out


def bs_straddle(
    s: npt.ArrayLike, k: npt.ArrayLike, t: npt.ArrayLike, sigma: npt.ArrayLike
) -> np.ndarray:
    """Black-Scholes straddle value with r = 0; intrinsic where t or sigma is zero."""
    sa, ka = np.asarray(s, dtype=float), np.asarray(k, dtype=float)
    ta, sg = np.asarray(t, dtype=float), np.asarray(sigma, dtype=float)
    vol = sg * np.sqrt(np.clip(ta, 0.0, None))
    with np.errstate(invalid="ignore", divide="ignore"):
        d1 = (np.log(sa / ka) + 0.5 * vol**2) / vol
        d2 = d1 - vol
        call = sa * norm.cdf(d1) - ka * norm.cdf(d2)
    put = call - sa + ka
    value = np.where(vol > 0, call + put, np.abs(sa - ka))
    return np.where(np.isnan(vol), np.nan, value)


def sharpe(x: np.ndarray) -> float:
    x = np.asarray(x, dtype=float)
    return float(x.mean() / x.std(ddof=1)) if len(x) > 1 and x.std(ddof=1) > 0 else float("nan")


def _keys(dates: pd.Series) -> np.ndarray:
    return pd.to_datetime(dates).dt.strftime("%Y-%m-%d").to_numpy()


def _boot(n: int, keys: np.ndarray, fn: Callable[[np.ndarray], float]) -> tuple[float, float]:
    """Date-clustered percentile bootstrap of ``fn`` evaluated on resampled row indices."""
    return cluster_bootstrap_ci(np.arange(n, dtype=float), keys, fn, n_boot=N_BOOT, seed=SEED)


# ── outcomes ─────────────────────────────────────────────────────────────────


def _outcomes(d: pd.DataFrame) -> pd.DataFrame:
    """Attach R_adj, both cost arms of net return on margin and premium, and the premium term.

    Expects per-event columns ``credit``, ``exit_mark`` (per share), ``k`` (shares), ``margin``,
    ``spot_exit``, ``strike``, ``t_exit``, ``back_atm_iv``.
    """
    bs = bs_straddle(d["spot_exit"], d["strike"], d["t_exit"], d["back_atm_iv"])
    d["bs_exit"] = bs
    d["r_adj"] = -(d["exit_mark"] - bs) * d["k"] / d["margin"]
    gross = (d["credit"] - d["exit_mark"]) * d["k"]
    cost_meas = (ENTRY_HALF * d["credit"] + EXIT_HALF * d["exit_mark"]) * d["k"]
    cost_116 = PREMIUM_ROUND_TRIP * d["credit"] * d["k"]
    prem = d["credit"] * d["k"]
    d["net_rom"] = (gross - cost_meas) / d["margin"]
    d["net_rom_116"] = (gross - cost_116) / d["margin"]
    d["net_rop"] = (gross - cost_meas) / prem
    d["net_rop_116"] = (gross - cost_116) / prem
    d["prem_term"] = prem / d["margin"]
    d["abs_logm"] = np.abs(np.log(d["spot_exit"] / d["strike"]))
    d["move_ratio"] = d["realised_move"] / d["implied_move"]
    return d


def panel_events() -> pd.DataFrame:
    p = pd.read_parquet(PANEL)
    d = pd.DataFrame(
        {
            "ticker": p["ticker"],
            "block": p["block"],
            "announce_date": pd.to_datetime(p["announce_date"]),
            "entry_date": pd.to_datetime(p["entry_date"]),
            "exit_date": pd.to_datetime(p["exit_date"]),
            "credit": p["credit_mkt"],
            "exit_mark": p["exit_mkt"],  # quote mark of the sold straddle at the exit close
            "k": p["contracts"] * 100,
            "margin": p["margin"],
            "spot_exit": p["spot_exit"],
            "strike": p["strike_mkt"],  # strike the marks were taken at (intr_exit agrees)
            "t_entry": p["t_entry"],
            "t_exit": p["t_exit"],
            "front_atm_iv": p["front_atm_iv"],
            "back_atm_iv": p["back_atm_iv"],
            "implied_move": p["implied_move"],
            "realised_move": p["realised_move"],
        }
    )
    return _outcomes(d)


def ledger_events() -> pd.DataFrame:
    """2025-2026 ledger joined to the event file that carries its at-entry IVs."""
    led = pd.read_csv(LEDGER, parse_dates=["announce_date", "entry_date", "exit_date", "expiry"])
    ev = pd.read_parquet(EVENTS_2025)
    for c in ("announce_date", "entry_date"):
        ev[c] = pd.to_datetime(ev[c])
    ev = ev[["ticker", "announce_date", "entry_date", "t_entry", "front_atm_iv", "back_atm_iv"]]
    j = led.merge(
        ev, on=["ticker", "announce_date", "entry_date"], how="inner", validate="one_to_one"
    )
    print(f"  ledger {len(led)}, joined to at-entry IVs {len(j)}")
    if len(j) < 0.95 * len(led):
        raise SystemExit("ledger join to the 2025 event file lost more than 5% of rows")
    d = pd.DataFrame(
        {
            "ticker": j["ticker"],
            "block": "confirmation_2025_2026",
            "announce_date": j["announce_date"],
            "entry_date": j["entry_date"],
            "exit_date": j["exit_date"],
            "credit": j["straddle_entry"],
            "exit_mark": j["straddle_exit"],
            "k": j["credit"] / j["straddle_entry"],
            "margin": j["margin"],
            "spot_exit": j["spot_exit"],
            "strike": j["strike"],
            "t_entry": j["t_entry"],
            "t_exit": (j["expiry"] - j["exit_date"]).dt.days / 365,
            "front_atm_iv": j["front_atm_iv"],
            "back_atm_iv": j["back_atm_iv"],
            "implied_move": j["implied_move"],
            "realised_move": j["realised_move"],
        }
    )
    return _outcomes(d)


def peer_table(include_2025: bool) -> pd.DataFrame:
    """Every announcement usable as a peer: ticker, season, exit session, J, move ratio."""
    p = pd.read_parquet(PANEL)
    frames = [p]
    if include_2025:
        frames.append(pd.read_parquet(EVENTS_2025))
    rows = []
    for f in frames:
        rows.append(
            pd.DataFrame(
                {
                    "ticker": f["ticker"].to_numpy(),
                    "announce_date": pd.to_datetime(f["announce_date"]).to_numpy(),
                    "exit_date": pd.to_datetime(f["exit_date"]).to_numpy(),
                    "J": np.sqrt(
                        priced_jump_var(
                            f["front_atm_iv"],
                            f["back_atm_iv"],
                            f["t_entry"],
                            f["t_entry"] + BACK_TENOR_FALLBACK,
                        )
                    ),
                    "move_ratio": (f["realised_move"] / f["implied_move"]).to_numpy(),
                }
            )
        )
    t = pd.concat(rows, ignore_index=True).drop_duplicates(["ticker", "announce_date"])
    t["season"] = t["announce_date"].map(season_start)
    return t.reset_index(drop=True)


# ── returns, clusters and SIC groups ─────────────────────────────────────────


def resolve_permnos(tickers: list[str]) -> tuple[dict[str, int], pd.DataFrame]:
    """Map each ticker to the permno of its latest CRSP name record (BRK-B to class B)."""
    from earnings_iv_crush.data import wrds_r2

    nm = wrds_r2.read_table("crsp_a_stock", "dsenames")
    nm["namedt"] = pd.to_datetime(nm["namedt"])
    nm["nameendt"] = pd.to_datetime(nm["nameendt"])
    out: dict[str, int] = {}
    for t in tickers:
        root, _, cls = t.partition("-")
        s = nm[nm["ticker"].isin({t, t.replace("-", ""), t.replace("-", "."), root})]
        if cls:
            s = s[s["shrcls"] == cls]
        if s.empty:
            print(f"  WARNING: {t} not found in CRSP dsenames - no returns, no SIC")
            continue
        out[t] = int(s.sort_values("nameendt").iloc[-1]["permno"])
    if not out:
        raise SystemExit("no ticker resolved to a CRSP permno")
    return out, nm[nm["permno"].isin(list(out.values()))].copy()


def crsp_log_returns(permnos: dict[str, int]) -> pd.DataFrame:
    """Daily log returns from CRSP ``dsf`` prices adjusted through ``cfacpr`` (dates x names)."""
    from earnings_iv_crush.data import wrds_r2

    df = wrds_r2.read_table(
        "crsp_a_stock",
        "dsf",
        columns=["permno", "date", "prc", "cfacpr"],
        filters=[
            ("permno", "in", sorted(set(permnos.values()))),
            ("date", ">=", RETURNS_START.date()),
            ("date", "<=", CRSP_END.date()),
        ],
    )
    if df.empty:
        raise SystemExit("CRSP dsf returned no rows for the universe")
    df["date"] = pd.to_datetime(df["date"])
    prc = pd.to_numeric(df["prc"], errors="coerce").astype(float).abs()
    cf = pd.to_numeric(df["cfacpr"], errors="coerce").astype(float)
    df["adj"] = prc.where(prc > 0) / cf.where(cf > 0)
    wide = df.pivot_table(index="date", columns="permno", values="adj").sort_index()
    inv = {v: k for k, v in permnos.items()}
    wide.columns = [inv[int(c)] for c in wide.columns]
    logp = pd.DataFrame(np.log(wide.to_numpy()), index=wide.index, columns=wide.columns)
    return logp.diff().iloc[1:]


def yf_log_returns(tickers: list[str], start: pd.Timestamp, end: pd.Timestamp) -> pd.DataFrame:
    import yfinance as yf

    raw = yf.download(
        tickers, start=str(start.date()), end=str(end.date()), auto_adjust=True, progress=False
    )
    close = raw["Close"] if isinstance(raw.columns, pd.MultiIndex) else raw[["Close"]]
    if not isinstance(raw.columns, pd.MultiIndex):
        close.columns = tickers
    close.index = pd.to_datetime(close.index).tz_localize(None)
    c = close.where(close > 0)
    logp = pd.DataFrame(np.log(c.to_numpy(dtype=float)), index=c.index, columns=c.columns)
    return logp.diff().iloc[1:]


def spliced_returns(crsp: pd.DataFrame, end: pd.Timestamp) -> pd.DataFrame:
    """CRSP through its last date, yfinance after; abort if the sources disagree by > 1 bp."""
    tickers = list(crsp.columns)
    yf_r = yf_log_returns(tickers, pd.Timestamp("2023-12-01"), end)
    overlap = crsp.index.intersection(yf_r.index)
    diff = (crsp.loc[overlap, tickers] - yf_r.loc[overlap, tickers]).abs().stack()
    med = float(np.nanmedian(diff.to_numpy(dtype=float)))
    print(f"  splice check: {len(overlap)} overlapping days, median |dr| {med * 1e4:.3f} bp")
    if not np.isfinite(med) or med > SPLICE_TOL:
        raise SystemExit(f"CRSP and yfinance returns disagree: median {med * 1e4:.3f} bp > 1 bp")
    tail = yf_r.loc[yf_r.index > crsp.index.max(), tickers]
    return pd.concat([crsp, tail])


def season_clusters(rets: pd.DataFrame, start: pd.Timestamp) -> tuple[dict[str, int], int, int]:
    """k-means++ clusters on market-residualised, standardised returns before ``start``."""
    from sklearn.cluster import KMeans

    w = rets.loc[rets.index < start].tail(WINDOW_DAYS)
    if len(w) < WINDOW_DAYS:
        raise SystemExit(f"season {start.date()}: only {len(w)} trading days before it")
    present = w.columns[w.notna().any()]
    w = w[present]
    total, count = w.sum(axis=1, min_count=1).fillna(0.0), w.notna().sum(axis=1)
    keep = [c for c in w.columns if w[c].notna().sum() >= MIN_VALID_RETURNS]
    rows = []
    for c in keep:
        y = w[c]
        m_others = (total - y.fillna(0.0)) / (count - y.notna().astype(int))
        ok = y.notna() & np.isfinite(m_others)
        x = np.column_stack([np.ones(ok.sum()), m_others[ok].to_numpy()])
        beta, *_ = np.linalg.lstsq(x, y[ok].to_numpy(), rcond=None)
        res = pd.Series(np.nan, index=w.index)
        res[ok] = y[ok].to_numpy() - x @ beta
        z = (res - res.mean()) / res.std(ddof=0)
        rows.append(z.fillna(0.0).to_numpy())  # a missing day sits at the series mean
    n = len(keep)
    k = int(round(n / NAMES_PER_CLUSTER))
    labels = KMeans(n_clusters=k, init="k-means++", n_init=KMEANS_N_INIT, random_state=0).fit(
        np.vstack(rows)
    )
    return dict(zip(keep, labels.labels_.tolist(), strict=True)), n, k


def season_sic2(names: pd.DataFrame, permnos: dict[str, int], start: pd.Timestamp) -> dict:
    """Two-digit SIC as of ``start``, carried forward from the last record before it."""
    out = {}
    for t, pn in permnos.items():
        s = names[(names["permno"] == pn) & (names["namedt"] <= start)].sort_values("namedt")
        if s.empty:
            continue
        sic = pd.to_numeric(s.iloc[-1]["siccd"], errors="coerce")
        if np.isfinite(sic) and sic > 0:
            out[t] = int(sic) // 100
    return out


def groups_by_season(
    seasons: list[pd.Timestamp],
    rets: pd.DataFrame,
    names: pd.DataFrame,
    permnos: dict[str, int],
) -> tuple[dict, dict, pd.DataFrame]:
    km, sic, log = {}, {}, []
    for s in sorted(set(seasons)):
        lab, n, k = season_clusters(rets, s)
        km[s] = lab
        sic[s] = season_sic2(names, permnos, s)
        sizes = pd.Series(lab).value_counts()
        log.append(
            {
                "season": s.date(),
                "names_clustered": n,
                "k": k,
                "min_cluster": int(sizes.min()),
                "max_cluster": int(sizes.max()),
                "singleton_clusters": int((sizes == 1).sum()),
                "names_with_sic": len(sic[s]),
                "sic2_groups": len(set(sic[s].values())),
            }
        )
    return km, sic, pd.DataFrame(log)


# ── candidates ───────────────────────────────────────────────────────────────


def _mates(groups: dict[str, int], ticker: str) -> set[str] | None:
    if ticker not in groups:
        return None
    g = groups[ticker]
    return {t for t, v in groups.items() if v == g}


def attach_candidates(
    ev: pd.DataFrame, peers: pd.DataFrame, km: dict, sic: dict, pool: set[str]
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Candidate values for every event; returns the events and a per-trial funnel."""
    ev = ev.copy()
    ev["season"] = ev["announce_date"].map(season_start)
    ev["J"] = np.sqrt(
        priced_jump_var(
            ev["front_atm_iv"],
            ev["back_atm_iv"],
            ev["t_entry"],
            ev["t_entry"] + BACK_TENOR_FALLBACK,
        )
    )
    pt = peers[peers["ticker"].isin(pool)]
    p_tk, p_se = pt["ticker"].to_numpy(), pt["season"].to_numpy(dtype="datetime64[ns]")
    p_ex, p_j = pt["exit_date"].to_numpy(dtype="datetime64[ns]"), pt["J"].to_numpy()
    p_mr = pt["move_ratio"].to_numpy()
    e_tk = [str(t) for t in ev["ticker"]]
    e_se = [pd.Timestamp(t) for t in ev["season"]]
    e_en = [pd.Timestamp(t) for t in ev["entry_date"]]
    e_j = ev["J"].to_numpy(dtype=float)

    spec = {
        TRIALS[0]: ("km", "A"),
        TRIALS[1]: ("km", "B"),
        TRIALS[2]: ("sic", "B"),
    }
    funnel = []
    for trial, (grp, cand) in spec.items():
        vals = np.full(len(ev), np.nan)
        n_grouped = n_peer = 0
        for i in range(len(ev)):
            tk, se, en, ji = e_tk[i], e_se[i], e_en[i], float(e_j[i])
            groups = (km if grp == "km" else sic).get(se, {})
            mates = _mates(groups, tk)
            if mates is None:
                continue
            n_grouped += 1
            m = eligible_peer_mask(p_tk, p_se, p_ex, tk, se, en, mates)
            if cand == "A":
                m &= np.isfinite(p_j)
            else:
                m &= np.isfinite(p_mr)
            if not m.any():
                continue
            n_peer += 1
            if cand == "A":
                med = float(np.median(p_j[m]))
                with np.errstate(divide="ignore"):
                    vals[i] = np.log(ji / med) if med > 0 and np.isfinite(ji) else np.nan
            else:
                vals[i] = -float(np.median(p_mr[m]))
        ev[trial] = vals
        funnel.append(
            {
                "trial": trial,
                "events": len(ev),
                "outcome_finite": int(np.isfinite(ev["r_adj"]).sum()),
                "name_grouped_in_season": n_grouped,
                "with_eligible_peer": n_peer,
                "candidate_defined": int((~np.isnan(vals)).sum()),
                "candidate_and_outcome": int(
                    ((~np.isnan(vals)) & np.isfinite(ev["r_adj"].to_numpy())).sum()
                ),
            }
        )
    return ev, pd.DataFrame(funnel)


# ── discovery ────────────────────────────────────────────────────────────────


def _bins(x: pd.Series, n: int) -> pd.Series:
    return pd.qcut(x.rank(method="first"), n, labels=list(range(1, n + 1))).astype(int)


def decile_table(d: pd.DataFrame, cand: str) -> pd.DataFrame:
    d = d.assign(decile=_bins(d[cand], 10))
    cols = ["r_adj", "net_rom", "net_rom_116", "net_rop", "prem_term", "abs_logm", "move_ratio"]
    t = d.groupby("decile").agg(
        n=("r_adj", "size"), cand_mean=(cand, "mean"), **{f"{c}_mean": (c, "mean") for c in cols}
    )
    return t.reset_index()


def full_and_causal_books(d: pd.DataFrame, cand: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    d = d.sort_values(["announce_date", "ticker"]).reset_index(drop=True)
    full = d[d[cand] >= np.quantile(d[cand], Q)]
    causal = d[causal_quantile_rule(d[cand].to_numpy(), d["announce_date"].to_numpy())]
    return full, causal


def discovery(d: pd.DataFrame, cand: str) -> tuple[dict, pd.DataFrame]:
    """The three discovery criteria for one trial on the discovery block."""
    d = d[np.isfinite(d["r_adj"]) & ~np.isnan(d[cand])].reset_index(drop=True)
    if len(d) < 50:
        raise SystemExit(f"{cand}: only {len(d)} discovery events - not a sort")
    dec = decile_table(d, cand)
    rho = float(spearmanr(dec["decile"], dec["r_adj_mean"]).statistic)

    d["quintile"] = _bins(d[cand], 5)
    tb = d[d["quintile"].isin([1, 5])].reset_index(drop=True)
    top = (tb["quintile"] == 5).to_numpy()
    r, keys = tb["r_adj"].to_numpy(), _keys(tb["entry_date"])

    def gap(idx: np.ndarray, v: np.ndarray = r) -> float:
        j = idx.astype(int)
        t, b = top[j], ~top[j]
        return float(v[j][t].mean() - v[j][b].mean()) if t.any() and b.any() else np.nan

    gap_r = gap(np.arange(len(tb)))
    gap_ci = _boot(len(tb), keys, gap)

    x_all = np.column_stack([np.ones(len(tb)), top.astype(float), tb["abs_logm"].to_numpy()])

    def coef(idx: np.ndarray) -> float:
        j = idx.astype(int)
        if top[j].all() or (~top[j]).all():
            return np.nan
        beta, *_ = np.linalg.lstsq(x_all[j], r[j], rcond=None)
        return float(beta[1])

    reg_b = coef(np.arange(len(tb)))
    reg_ci = _boot(len(tb), keys, coef)

    gap_net = gap(np.arange(len(tb)), tb["net_rom"].to_numpy())
    gap_prem = gap(np.arange(len(tb)), tb["prem_term"].to_numpy())
    share = gap_prem / gap_net if gap_net > 0 else np.nan

    full, causal = full_and_causal_books(d, cand)
    m_full, m_causal = float(full["r_adj"].mean()), float(causal["r_adj"].mean())
    ratio = m_causal / m_full if m_full != 0 else np.nan

    c1 = bool(rho >= SPEARMAN_MIN and (gap_ci[0] > 0 or gap_ci[1] < 0))
    c2 = bool((reg_ci[0] > 0 or reg_ci[1] < 0) and gap_net > 0 and share < PREMIUM_SHARE_MAX)
    c3 = bool(np.isfinite(ratio) and ratio >= CAUSAL_RATIO_MIN)
    res = {
        "trial": cand,
        "n_eligible": len(d),
        "n_dates": int(pd.Series(_keys(d["entry_date"])).nunique()),
        "decile_spearman_r_adj": rho,
        "n_top_quintile": int(top.sum()),
        "n_bottom_quintile": int((~top).sum()),
        "tmb_r_adj": gap_r,
        "tmb_r_adj_ci_low": gap_ci[0],
        "tmb_r_adj_ci_high": gap_ci[1],
        "c1_ordering": c1,
        "reg_top_coef_r_adj": reg_b,
        "reg_top_ci_low": reg_ci[0],
        "reg_top_ci_high": reg_ci[1],
        "tmb_net_rom": gap_net,
        "tmb_prem_term": gap_prem,
        "premium_share_of_net_gap": share,
        "c2_right_driver": c2,
        "n_full_book": len(full),
        "full_book_mean_r_adj": m_full,
        "n_causal_book": len(causal),
        "causal_book_mean_r_adj": m_causal,
        "causal_over_full": ratio,
        "c3_causal_agreement": c3,
        "passes_discovery": bool(c1 and c2 and c3),
    }
    return res, dec


# ── books, null and validation ───────────────────────────────────────────────


def matched_null(d: pd.DataFrame, book: pd.DataFrame) -> pd.DataFrame:
    """Participation-matched random draw: the book's trade count per season, seed 0."""
    rng = np.random.default_rng(SEED)
    parts = []
    for s, n in book.groupby("season").size().items():
        pool = d[d["season"] == s]
        parts.append(pool.iloc[rng.choice(len(pool), size=int(n), replace=False)])
    return pd.concat(parts) if parts else d.iloc[:0]


def book_stats(label: str, b: pd.DataFrame, sr_std: float) -> dict:
    x = b["net_rom"].to_numpy()
    keys = _keys(b["entry_date"])
    span = (b["entry_date"].max() - b["entry_date"].min()).days / 365.25 if len(b) > 1 else np.nan
    tpy = len(b) / span if span and span > 0 else np.nan
    row: dict = {"book": label, "n": len(b), "trades_per_year": tpy}
    for c in ("r_adj", "net_rom", "net_rom_116", "net_rop", "net_rop_116"):
        v = b[c].to_numpy()
        row[f"mean_{c}"] = float(v.mean()) if len(v) else np.nan
        lo, hi = cluster_bootstrap_ci(v, keys, np.mean, n_boot=N_BOOT, seed=SEED)
        row[f"mean_{c}_ci_low"], row[f"mean_{c}_ci_high"] = lo, hi
    row["sharpe_net_rom"] = sharpe(x)
    row["sharpe_ci_low"], row["sharpe_ci_high"] = cluster_bootstrap_ci(
        x, keys, sharpe, n_boot=N_BOOT, seed=SEED
    )
    row["sharpe_net_rom_116"] = sharpe(b["net_rom_116"].to_numpy())
    row["sharpe_annualised_own_cadence"] = row["sharpe_net_rom"] * np.sqrt(tpy)
    for n_tr, tag in ((DSR_TRIALS, "dsr_1489"), (LEDGER_TRIALS_NOW, "dsr_1503")):
        row[tag] = float(deflated_sharpe_ratio(pd.Series(x), n_trials=n_tr, sr_trials_std=sr_std))
    return row


def sharpe_difference(book: pd.DataFrame, null: pd.DataFrame) -> tuple[float, float, float]:
    """Sharpe(book) minus Sharpe(null) on net RoM with a joint date-clustered CI."""
    st = pd.concat([book.assign(_g=1), null.assign(_g=0)], ignore_index=True)
    g, x = st["_g"].to_numpy(), st["net_rom"].to_numpy()

    def diff(idx: np.ndarray) -> float:
        j = idx.astype(int)
        return sharpe(x[j][g[j] == 1]) - sharpe(x[j][g[j] == 0])

    lo, hi = _boot(len(st), _keys(st["entry_date"]), diff)
    return diff(np.arange(len(st))), lo, hi


def hold_out_test(d: pd.DataFrame, cand: str, label: str, sr_std: float) -> tuple[dict, list]:
    """Validation or confirmation test: causal q=0.80 book against its matched null."""
    d = d[np.isfinite(d["r_adj"]) & ~np.isnan(d[cand])]
    d = d.sort_values(["announce_date", "ticker"]).reset_index(drop=True)
    book = d[causal_quantile_rule(d[cand].to_numpy(), d["announce_date"].to_numpy())]
    if len(book) < 3:
        raise SystemExit(f"{label}/{cand}: causal book has {len(book)} trades - not a test")
    null = matched_null(d, book)
    dsr, lo, hi = sharpe_difference(book, null)
    passed = bool(lo > 0 and book["r_adj"].mean() > 0)
    res = {
        "stage": label,
        "trial": cand,
        "n_eligible": len(d),
        "n_book": len(book),
        "n_null": len(null),
        "sharpe_diff_net_rom": dsr,
        "sharpe_diff_ci_low": lo,
        "sharpe_diff_ci_high": hi,
        "book_mean_r_adj": float(book["r_adj"].mean()),
        "passes": passed,
    }
    books = [
        {"stage": label, "trial": cand, **book_stats("causal_q80", book, sr_std)},
        {"stage": label, "trial": cand, **book_stats("matched_null", null, sr_std)},
    ]
    return res, books


# ── entry point ──────────────────────────────────────────────────────────────


def _universe() -> list[str]:
    from earnings_iv_crush.data.universe import MEGACAP_50

    return list(MEGACAP_50)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[2])
    ap.add_argument("--out", type=Path, default=OUT)
    args = ap.parse_args()
    out: Path = args.out
    digest = check_prereg()
    out.mkdir(parents=True, exist_ok=True)
    sr_std = float(pd.read_csv(PERF).iloc[0]["sr_trials_std"])

    mega = _universe()
    ev = panel_events()
    unknown = sorted(set(ev["ticker"]) - set(mega))
    if unknown:
        raise SystemExit(f"panel names outside the megacap universe: {unknown}")

    permnos, names = resolve_permnos(mega)
    rets = crsp_log_returns(permnos)
    print(f"  CRSP returns: {rets.shape[0]} days x {rets.shape[1]} names, to {rets.index.max()}")
    peers = peer_table(include_2025=False)
    seasons = list(ev["announce_date"].map(season_start).unique())
    km, sic, clog = groups_by_season(seasons, rets, names, permnos)
    clog.to_csv(out / "clusters_by_season.csv", index=False)

    ev, funnel = attach_candidates(ev, peers, km, sic, set(mega))
    funnels = []
    for blk in (DISCOVERY, VALIDATION):
        sub = ev[ev["block"] == blk]
        _, f = attach_candidates(sub.drop(columns=list(TRIALS)), peers, km, sic, set(mega))
        funnels.append(f.assign(block=blk))
    funnel_all = pd.concat(funnels, ignore_index=True)
    print(funnel_all.to_string(index=False))
    if (funnel_all["candidate_and_outcome"] == 0).any():
        raise SystemExit("a trial has no scoreable event in a block - empty join")

    # Sanity check on the outcome definition against the figure stated in the prereg.
    disc = ev[(ev["block"] == DISCOVERY) & np.isfinite(ev["r_adj"])]
    rho_check = float(spearmanr(disc["r_adj"], disc["move_ratio"]).statistic)
    print(f"  R_adj vs realised/implied, discovery, all events: Spearman {rho_check:+.3f}")

    # 1. Discovery, all three trials.
    disc_rows, decs = [], []
    for t in TRIALS:
        res, dec = discovery(ev[ev["block"] == DISCOVERY], t)
        disc_rows.append(res)
        decs.append(dec.assign(trial=t))
    disc_res = pd.DataFrame(disc_rows)
    disc_res.to_csv(out / "discovery_criteria.csv", index=False)
    pd.concat(decs, ignore_index=True).to_csv(out / "discovery_deciles.csv", index=False)
    print(disc_res.T.to_string())

    # Descriptive books on discovery (both thresholds) for every trial.
    books = []
    for t in TRIALS:
        d = ev[(ev["block"] == DISCOVERY) & np.isfinite(ev["r_adj"]) & ~np.isnan(ev[t])]
        full, causal = full_and_causal_books(d, t)
        for lab, b in (("eligible_all", d), ("full_q80", full), ("causal_q80", causal)):
            books.append({"stage": "discovery", "trial": t, **book_stats(lab, b, sr_std)})

    # 2. Validation, only for a trial that passed every discovery criterion.
    val_rows = []
    for t in disc_res.loc[disc_res["passes_discovery"], "trial"]:
        res, bk = hold_out_test(ev[ev["block"] == VALIDATION], t, "validation", sr_std)
        val_rows.append(res)
        books += bk
    val_res = pd.DataFrame(val_rows)

    # 3. Confirmation, only for a trial that passed validation.
    conf_rows = []
    passed_val = list(val_res.loc[val_res["passes"], "trial"]) if len(val_res) else []
    if passed_val:
        led = ledger_events()
        all_names = sorted(set(pd.read_parquet(EVENTS_2025)["ticker"]) | set(mega))
        permnos2, names2 = resolve_permnos(all_names)
        rets2 = spliced_returns(crsp_log_returns(permnos2), pd.Timestamp("2026-07-01"))
        peers2 = peer_table(include_2025=True)
        seas2 = list(led["announce_date"].map(season_start).unique())
        mega_cols = [c for c in rets2.columns if c in set(mega)]
        km_m, sic_m, _ = groups_by_season(seas2, rets2[mega_cols], names2, permnos2)
        km_a, sic_a, _ = groups_by_season(seas2, rets2, names2, permnos2)
        led_m = led[led["ticker"].isin(mega)]
        e_m, f_m = attach_candidates(led_m, peers2, km_m, sic_m, set(mega))
        e_a, f_a = attach_candidates(led, peers2, km_a, sic_a, set(all_names))
        funnel_all = pd.concat(
            [funnel_all, f_m.assign(block="conf_megacap"), f_a.assign(block="conf_all")]
        )
        for t in passed_val:
            r1, b1 = hold_out_test(e_m, t, "confirmation_megacap_primary", sr_std)
            r2, b2 = hold_out_test(e_a, t, "confirmation_all_secondary", sr_std)
            conf_rows += [r1, r2]
            books += b1 + b2
    conf_res = pd.DataFrame(conf_rows)

    funnel_all.to_csv(out / "funnel.csv", index=False)
    pd.DataFrame(books).to_csv(out / "books.csv", index=False)
    if len(val_res):
        val_res.to_csv(out / "validation.csv", index=False)
    if len(conf_res):
        conf_res.to_csv(out / "confirmation.csv", index=False)

    verdict: dict = {
        "prereg_sha256": digest,
        "dsr_trial_count": DSR_TRIALS,
        "programme_ledger_now": LEDGER_TRIALS_NOW,
        "outcome_check_spearman_r_adj_vs_move_ratio": rho_check,
        "trials": {},
    }
    for r in disc_rows:
        t = r["trial"]
        v: dict[str, Any] = {
            "discovery": {
                k: r[k]
                for k in (
                    "c1_ordering",
                    "c2_right_driver",
                    "c3_causal_agreement",
                    "passes_discovery",
                )
            }
        }
        stages = ["discovery"]
        if r["passes_discovery"]:
            vr = val_res[val_res["trial"] == t].iloc[0]
            v["validation_passes"] = bool(vr["passes"])
            stages.append("validation")
            if vr["passes"]:
                cr = conf_res[conf_res["trial"] == t]
                v["confirmation"] = {row["stage"]: bool(row["passes"]) for _, row in cr.iterrows()}
                stages.append("confirmation")
        prim = v.get("confirmation", {}).get("confirmation_megacap_primary", False)
        v["stages_run"] = stages
        v["verdict"] = "confirmed" if prim else f"failed_{stages[-1]}"
        verdict["trials"][t] = v
    (out / "verdict.json").write_text(json.dumps(verdict, indent=2, default=str))
    print(json.dumps(verdict, indent=2, default=str))
    print(f"  wrote {out.resolve()}")


if __name__ == "__main__":
    main()
