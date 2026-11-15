"""
shadow.py
The shadow book: what each real paper trade would have earned under the alternatives worth
watching, marked on the trade's own fills and quotes, never traded.

For every closed transmitted trade it reports, on the research margin unit
``m0 = 0.20 x spot_entry + entry fill`` (per share):

* ``B_real``: the realised trade (entry fill, next-session buy-back fill, commissions);
* ``H_shadow``: the same sale delta-hedged with stock from the reaction-session close and
  settled at intrinsic on expiry, valued with ``research.hedged_hold.hedged_short_straddle``
  as the hedged-event-hold study does (hedge volatility from the reaction-session 15:59
  straddle mid, equity half-spread from ``SHADOW``), except that the assigned share nets
  against the hedge at expiry (``HEDGED_NET``, adopted 2026-11-13);
* ``g1``: whether the trade passes the G1 gate on the book's own strictly earlier trades.

Nothing here connects to a broker or writes a record the order path reads. Stock paths come
from an injected fetcher, so tests run offline.

References
----------
Bakshi, G. and Kapadia, N. (2003). Delta-hedged gains and the negative market volatility risk
premium. Review of Financial Studies 16(2), 527-566.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import numpy as np
import pandas as pd

from ..config import HEDGED, HEDGED_NET, SHADOW, ShadowConfig
from ..engine.pnl import CONTRACT_MULTIPLIER
from ..engine.stats import nyse_sessions
from ..research.hedged_hold import hedged_short_straddle, straddle_iv, year_frac

MARGIN_SPOT_FRAC = 0.20  # the research margin unit m0, as in the hedged-event-hold study
KEYS = ["ticker", "entry_date"]

#: ticker, first session, last session -> frame indexed by session date with columns
#: ``prc`` (as-traded close), ``ret`` (total return from the previous close), ``cfacpr``
#: (split factor; a change inside the hold invalidates the path).
PathFetcher = Callable[[str, pd.Timestamp, pd.Timestamp], pd.DataFrame]

COLUMNS = [
    "ticker",
    "entry_date",
    "exit_date",
    "expiry",
    "strike",
    "contracts",
    "status",
    "m0_ps",
    "B_real",
    "H_shadow",
    "H_mid_shadow",
    "H_minus_B",
    "hedge_sigma",
    "n_hedge",
    "iv_term_spread_nearest",
    "entry_rel_spread",
    "g1",
]


# ── inputs ───────────────────────────────────────────────────────────────────


def closed_trades(
    open_path: str, nostop_path: str, recon_path: str, *, transmitted_only: bool = True
) -> pd.DataFrame:
    """Closed trades (transmitted only, unless reading the dry stores) with entry fields, buy-back fill and the exit mid.

    Raises if a ledger row has no position or no reconciliation row: a join that drops
    trades silently would make the shadow book depend on whatever broke it.
    """
    if not Path(nostop_path).exists():
        return pd.DataFrame()
    led = pd.read_parquet(nostop_path)
    pos = pd.read_parquet(open_path)
    rec = pd.read_parquet(recon_path)
    for f in (led, pos, rec):
        f["entry_date"] = pd.to_datetime(f["entry_date"]).dt.normalize()
    if transmitted_only and "transmitted" in pos.columns:
        pos = pos[pos["transmitted"].fillna(False).astype(bool)]
    want = [
        "announce_date",
        "front_expiry",
        "entry_fill_ps",
        "entry_mid_ps",
        "iv_term_spread_nearest",
        "entry_rel_spread",
    ]
    pos = pos[KEYS + [c for c in want if c in pos.columns]].drop_duplicates(KEYS)
    rec = rec[KEYS + ["assumed_mid_mark_ps", "nostop_fill_ps"]].drop_duplicates(KEYS)
    d = led.merge(pos, on=KEYS, how="left", validate="many_to_one", indicator="_p")
    d = d.merge(rec, on=KEYS, how="left", validate="many_to_one", indicator="_r")
    lost = int(((d["_p"] != "both") | (d["_r"] != "both")).sum())
    if lost:
        raise ValueError(
            f"{lost} of {len(led)} ledger trades lack a position or reconciliation row"
        )
    for c in want:
        if c not in d.columns:
            d[c] = np.nan
    return d.drop(columns=["_p", "_r"]).sort_values(["entry_date", "ticker"]).reset_index(drop=True)


# ── one trade ────────────────────────────────────────────────────────────────


def _per_share(trade: pd.Series, col: str) -> float:
    return float(trade[col]) / (CONTRACT_MULTIPLIER * int(trade["contracts"]))


def shadow_trade(trade: pd.Series, path: pd.DataFrame | None, cfg: ShadowConfig = SHADOW) -> dict:
    """B_real and H_shadow for one closed trade; ``status`` says why H is missing."""
    k = float(trade["strike"])
    exp = pd.Timestamp(trade["front_expiry"]).normalize()
    t1 = pd.Timestamp(trade["exit_date"]).normalize()
    s0 = _per_share(trade, "entry_credit")
    m0 = MARGIN_SPOT_FRAC * float(trade["spot_entry"]) + s0
    b_real = float(trade["pnl"]) / (CONTRACT_MULTIPLIER * int(trade["contracts"])) / m0
    mid0 = float(trade["entry_mid_ps"]) if np.isfinite(trade["entry_mid_ps"]) else s0
    out = {
        "expiry": exp,
        "m0_ps": m0,
        "B_real": b_real,
        "H_shadow": np.nan,
        "H_mid_shadow": np.nan,
        "hedge_sigma": np.nan,
        "n_hedge": np.nan,
    }
    if path is None:
        return {**out, "status": "pending"}
    sess = nyse_sessions(t1, exp)
    if len(sess) == 0 or sess[0] != t1:
        return {**out, "status": "exit_not_session"}
    g = path.reindex(sess)
    if g["prc"].isna().any() or (g["prc"] <= 0).any() or g["ret"].iloc[1:].isna().any():
        return {**out, "status": "missing_close"}
    if g["cfacpr"].nunique() > 1:
        return {**out, "status": "split_in_hold"}

    closes = g["prc"].to_numpy(float)
    settle = float(closes[-1])
    intrinsic = abs(settle - k)
    n_hedge = len(closes) - 1
    fee = HEDGED.fee_per_contract_leg / CONTRACT_MULTIPLIER
    disposal = HEDGED.disposal_bps / 1e4 * settle if intrinsic > 0 else 0.0
    if n_hedge == 0:
        net, gross_mid, sigma = s0 - intrinsic - 2 * fee - disposal, mid0 - intrinsic, np.nan
    else:
        mid_x = float(trade["assumed_mid_mark_ps"])
        sigma = straddle_iv(mid_x, float(trade["spot_exit"]), k, year_frac(t1, exp))
        if not np.isfinite(sigma):
            # A mid at or under intrinsic has no implied vol; the exit pass's own ATM IV is
            # the next quote-based value, as the research study fell back to its s2 IV.
            sigma = float(trade.get("iv_exit", np.nan))
        if not np.isfinite(sigma) or sigma <= 0:
            return {**out, "status": "no_hedge_vol"}
        hs = np.full(n_hedge, cfg.equity_half_spread_bps / 1e4)
        r = hedged_short_straddle(
            sale_price=s0,
            sale_mid=mid0,
            strike=k,
            fwd=float(trade["spot_entry"]),
            closes=closes[:-1],
            rets=g["ret"].to_numpy(float)[1:],
            taus=np.array([year_frac(d, exp) for d in g.index[:-1]]),
            sigmas=np.full(n_hedge, sigma),
            half_spreads=hs,
            settle_close=settle,
            cfg=HEDGED_NET,
        )
        net, gross_mid = r.net_pnl, r.gross_pnl_mid
    return {
        **out,
        "status": "ok",
        "H_shadow": net / m0,
        "H_mid_shadow": gross_mid / m0,
        "hedge_sigma": sigma,
        "n_hedge": n_hedge,
    }


# ── the gate flag ────────────────────────────────────────────────────────────


def g1_flags(d: pd.DataFrame, cfg: ShadowConfig = SHADOW) -> pd.Series:
    """G1 on the book's own strictly earlier trades; NaN while warming up or unrecorded."""
    t = pd.to_datetime(d["announce_date"]).to_numpy()
    term = d["iv_term_spread_nearest"].to_numpy(float)
    spr = d["entry_rel_spread"].to_numpy(float)
    out = np.full(len(d), np.nan)
    for i in range(len(d)):
        if not (np.isfinite(term[i]) and np.isfinite(spr[i])):
            continue
        prior = (t < t[i]) & np.isfinite(term) & np.isfinite(spr)
        if prior.sum() < cfg.gate_min_prior:
            continue
        q_t = np.quantile(term[prior], cfg.gate_term_q)
        q_s = np.quantile(spr[prior], cfg.gate_spread_q)
        out[i] = float(term[i] >= q_t and spr[i] <= q_s)
    return pd.Series(out, index=d.index)


# ── the book ─────────────────────────────────────────────────────────────────


def build_shadow(
    trades: pd.DataFrame, fetch: PathFetcher, asof: pd.Timestamp, cfg: ShadowConfig = SHADOW
) -> pd.DataFrame:
    """One row per closed trade; H stays ``pending`` until the expiry close has printed."""
    if trades.empty:
        return pd.DataFrame(columns=COLUMNS)
    rows = []
    for _, tr in trades.iterrows():
        exp = pd.Timestamp(tr["front_expiry"]).normalize()
        path = None
        if exp < asof.normalize():
            path = fetch(str(tr["ticker"]), pd.Timestamp(tr["exit_date"]).normalize(), exp)
        rows.append(
            {
                "ticker": tr["ticker"],
                "entry_date": tr["entry_date"],
                "exit_date": pd.Timestamp(tr["exit_date"]).normalize(),
                "strike": float(tr["strike"]),
                "contracts": int(tr["contracts"]),
                "iv_term_spread_nearest": tr["iv_term_spread_nearest"],
                "entry_rel_spread": tr["entry_rel_spread"],
                **shadow_trade(tr, path, cfg),
            }
        )
    out = pd.DataFrame(rows)
    out["H_minus_B"] = out["H_shadow"] - out["B_real"]
    out["g1"] = g1_flags(trades, cfg).to_numpy()
    return out[COLUMNS]


def summary(book: pd.DataFrame) -> str:
    """Funnel and means; descriptive only, never a verdict."""
    if book.empty:
        return "shadow book: no closed transmitted trades yet"
    ok = book[book["status"] == "ok"]
    lines = [
        f"shadow book: {len(book)} closed trades; status "
        + ", ".join(f"{k} {v}" for k, v in book["status"].value_counts().items()),
        f"  B_real mean {book['B_real'].mean():+.4f} of m0 per trade (N={len(book)})",
    ]
    if len(ok):
        lines.append(
            f"  on the {len(ok)} with H marked: B_real {ok['B_real'].mean():+.4f}, "
            f"H_shadow {ok['H_shadow'].mean():+.4f}, H minus B {ok['H_minus_B'].mean():+.4f}"
        )
    g = book["g1"]
    lines.append(
        f"  G1: {int((g == 1).sum())} pass, {int((g == 0).sum())} fail, "
        f"{int(g.isna().sum())} not scored (warm-up or feature not recorded)"
    )
    lines.append("  descriptive only: small N, delayed quotes; never read as a verdict")
    return "\n".join(lines)
