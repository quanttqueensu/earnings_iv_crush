"""price_windows.py: price every fetched window as a short ATM straddle and compute event measures.

Per window: parity forward at entry and exit, the traded contract (first common expiry at least
2 days after exit, common strike nearest the entry forward), P&L net at the touch and gross at the
mid, the IV change on the traded contract, the implied event jump from the entry term structure,
and the realised move. Screens: earnings date inside the window, another listed event of the same
name inside a control window. Every drop is counted in the funnel.

Output: windows_priced.parquet.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

MIN_DTE_AFTER_EXIT = 2  # avoid pricing a buy-back on expiry-day gamma
# Round 2: traded strike within 3% of the entry parity forward (round 1 had no tolerance and
# priced a 250 strike against a 355 forward on BIIB). None reproduces round 1.
ATM_TOL: float | None = 0.03
WIN_IN, WIN_OUT = "windows2.csv", "windows2_priced.parquet"


def load(t: str, d: pd.Timestamp) -> pd.DataFrame:
    c = pd.read_parquet(f"chains/{t}_{d:%Y-%m-%d}.parquet")
    c = c.assign(expiry=pd.to_datetime(c["expiration"]), strike=c["strike"].astype(float),
                 right=c["call_put"].str[0].str.upper(), bid=pd.to_numeric(c["bid"]),
                 ask=pd.to_numeric(c["ask"]), iv=pd.to_numeric(c["vol"]))
    return c[["expiry", "strike", "right", "bid", "ask", "iv"]]


def pair(c: pd.DataFrame, e: pd.Timestamp) -> pd.DataFrame:
    x = c[c["expiry"] == e]
    p = x.pivot_table(index="strike", columns="right", values=["bid", "ask", "iv"], aggfunc="first")
    p.columns = [f"{a}_{b}" for a, b in p.columns]
    need = ["bid_C", "ask_C", "bid_P", "ask_P", "iv_C", "iv_P"]
    if not set(need) <= set(p.columns):
        return pd.DataFrame(columns=need)
    return p[need].dropna(subset=["ask_C", "ask_P"])


def forward(p: pd.DataFrame) -> float:
    two = p[(p["bid_C"] > 0) & (p["bid_P"] > 0)]
    if two.empty:
        return np.nan
    mc = (two["bid_C"] + two["ask_C"]) / 2
    mp = (two["bid_P"] + two["ask_P"]) / 2
    k = (mc - mp).abs().idxmin()
    return float(k + mc[k] - mp[k])


def atm_iv(p: pd.DataFrame, f: float) -> float:
    if p.empty or not np.isfinite(f):
        return np.nan
    k = (pd.Series(p.index, index=p.index) - f).abs().idxmin()
    v = p.loc[k, ["iv_C", "iv_P"]].astype(float)
    return float(v.mean()) if v.notna().all() and (v > 0).all() else np.nan


def price(t: str, entry: pd.Timestamp, exit_: pd.Timestamp, ev_date: pd.Timestamp) -> dict:
    c0, c1 = load(t, entry), load(t, exit_)
    common = sorted(set(c0["expiry"]) & set(c1["expiry"]))
    common = [e for e in common if e >= exit_ + pd.Timedelta(days=MIN_DTE_AFTER_EXIT)]
    if not common:
        return {"price_status": "no_common_expiry"}
    chosen = None
    for e in common:
        p0, p1 = pair(c0, e), pair(c1, e)
        f0, f1 = forward(p0), forward(p1)
        if not (np.isfinite(f0) and np.isfinite(f1)):
            continue
        ks = sorted(set(p0.index) & set(p1.index))
        if not ks:
            continue
        k = min(ks, key=lambda s: abs(s - f0))
        if ATM_TOL is None or abs(k / f0 - 1) <= ATM_TOL:
            chosen = (e, p0, p1, f0, f1, k)
            break
    if chosen is None:
        return {"price_status": "no_atm_common_contract"}
    e, p0, p1, f0, f1, k = chosen
    a, b = p0.loc[k], p1.loc[k]
    out: dict = {"expiry": e, "strike": k, "f0": f0, "f1": f1,
                 "moneyness": k / f0 - 1, "dte_entry": (e - entry).days}
    bid0 = a["bid_C"] + a["bid_P"]
    ask0 = a["ask_C"] + a["ask_P"]
    if not (a["bid_C"] > 0 and a["bid_P"] > 0):
        return {**out, "price_status": "entry_one_sided"}
    mid0 = (bid0 + ask0) / 2
    ask1 = b["ask_C"] + b["ask_P"]
    two1 = b["bid_C"] > 0 and b["bid_P"] > 0
    mid1 = (b["bid_C"] + b["bid_P"] + ask1) / 2 if two1 else np.nan
    m0 = 0.20 * f0 + bid0
    iv0 = np.nanmean([a["iv_C"], a["iv_P"]])
    iv1 = np.nanmean([b["iv_C"], b["iv_P"]])
    # implied event jump: two earliest entry expiries after the event date
    exps = sorted(x for x in c0["expiry"].unique() if x > ev_date)
    jump2 = np.nan
    if len(exps) >= 2:
        s1, s2 = atm_iv(pair(c0, exps[0]), f0), atm_iv(pair(c0, exps[1]), f0)
        t1, t2 = (exps[0] - entry).days / 365, (exps[1] - entry).days / 365
        if np.isfinite(s1) and np.isfinite(s2) and t2 > t1 > 0:
            sd2 = (s2**2 * t2 - s1**2 * t1) / (t2 - t1)
            jump2 = s1**2 * t1 - sd2 * t1
            out.update({"sig1": s1, "sig2": s2, "sigd2": sd2})
    dt = (exit_ - entry).days / 365
    sd2 = out.get("sigd2", np.nan)
    diff_var = max(sd2, 0.0) * dt if np.isfinite(sd2) else np.nan
    impl_abs = np.sqrt(2 / np.pi) * np.sqrt(max(jump2, 0.0) + diff_var) \
        if np.isfinite(jump2) and np.isfinite(diff_var) else np.nan
    out.update({
        "price_status": "ok", "bid0": bid0, "ask0": ask0, "mid0": mid0, "ask1": ask1,
        "mid1": mid1, "m0": m0,
        "pnl_touch_m0": (bid0 - ask1) / m0, "pnl_mid_m0": (mid0 - mid1) / m0,
        "pnl_touch_prem": (bid0 - ask1) / mid0, "pnl_mid_prem": (mid0 - mid1) / mid0,
        "spread_cost_m0": ((mid0 - bid0) + (ask1 - mid1)) / m0 if two1 else np.nan,
        "iv0": iv0, "iv1": iv1, "crush_vp": 100 * (iv0 - iv1),
        "jump2": jump2, "impl_jump_abs": np.sqrt(2 / np.pi) * np.sqrt(max(jump2, 0.0))
        if np.isfinite(jump2) else np.nan,
        "impl_abs_window": impl_abs, "real_abs": abs(np.log(f1 / f0)),
        "entry_halfspread_prem": (mid0 - bid0) / mid0,
    })
    return out


def main() -> None:
    w = pd.read_csv(WIN_IN, parse_dates=["event_date", "entry", "exit"])
    ev = pd.read_csv("events.csv", parse_dates=["event_date"])
    ed = pd.read_parquet("earnings_dates.parquet")
    w = w.merge(ev[["event_id", "category", "sub", "material"]], on="event_id", how="left")
    w["orig_date"] = w["event_date"] - pd.to_timedelta(w["shift"], unit="D")
    rows = []
    for _, r in w.iterrows():
        rec = r.to_dict()
        if r["status"] != "ok":
            rec["price_status"] = r["status"]
        else:
            rec.update(price(r["ticker"], r["entry"], r["exit"], r["event_date"]))
        e_t = ed.loc[ed["ticker"] == r["ticker"], "edate"]
        rec["earn_screened"] = len(e_t) > 0
        if r["status"] == "ok":
            rec["earn_in_window"] = bool(((e_t >= r["entry"]) & (e_t <= r["exit"])).any())
            other = ev[(ev["ticker"] == r["ticker"])]["event_date"]
            rec["other_event_in_window"] = bool(r["shift"] != 0 and (
                (other >= r["entry"] - pd.Timedelta(days=2)) &
                (other <= r["exit"] + pd.Timedelta(days=2))).any())
        rows.append(rec)
    out = pd.DataFrame(rows)
    out["block"] = np.where(out["orig_date"] < "2022-01-01", "disc_2019_21", "held_2022_24")
    out.to_parquet(WIN_OUT)
    # funnel
    for cat, g in out.groupby("category"):
        e = g[g["shift"] == 0]
        print(f"\n== {cat}: event windows {len(e)}")
        print(e["price_status"].value_counts().to_string())
        ok = e[e["price_status"] == "ok"]
        print("priced ok", len(ok), "| earnings in window", int(ok["earn_in_window"].sum()),
              "| unscreened", int((~ok["earn_screened"]).sum()))
        c = g[g["shift"] != 0]
        print("controls", len(c), "priced ok", int((c["price_status"] == "ok").sum()),
              "| dropped for earnings", int(c["earn_in_window"].fillna(False).sum()),
              "| other event", int(c["other_event_in_window"].fillna(False).sum()))


if __name__ == "__main__":
    main()
