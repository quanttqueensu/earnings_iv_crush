"""
d1data.py
Lane D1 data assembly: D0's targets, L4's causal prior-predictive inputs, L4's seven
causally standardised 15:59 features and D0's surface tensor, joined one-to-one on ticker and
entry date, with the development mask on outcomes and the block-view log.

Development mode blanks every outcome (``H_net``, ``residual_value``) of an event entered on or
after 1 January 2019 before anything else reads it, and reads ``l4_scores.parquet`` only for
rows entered in 2018 or earlier. The held-out scorer loads with ``mode="heldout"``, which logs
the views of 2019-24 (and, with ``with_2025=True``, 2025-26) with a UTC clock stamp taken when
the rows are loaded.

Basis: ``y`` is ``H_net`` in % of m0 per trade, net at the touch, not annualised; ``rv`` is
``residual_value`` in % of m0; ``U`` is ``U_pct`` (100 s0 / m0).

Usage
-----
    import d1data; D = d1data.load("dev")
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import d1lib  # noqa: F401  (imports pyarrow before torch)
import numpy as np
import pandas as pd

from earnings_iv_crush.research import online_bayes as ob
from earnings_iv_crush.research.protocol import log_block_view, sha256_file

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
D0 = HERE.parent / "D0-surface"
TARGETS = D0 / "targets.parquet"
L4_INPUTS = D0 / "l4_inputs.parquet"
L4_SCORES = D0 / "l4_scores.parquet"
READY = D0 / "SURFACES_READY.txt"
PANEL = ROOT / "outputs/research/2026-11-13-alpha-hunt-2/laneE-walk-forward-model/panel.parquet"
BLOCKS_VIEWED = HERE / "blocks_viewed.csv"
KEYS = ["ticker", "entry_date"]
DEV_END = pd.Timestamp("2019-01-01")
#: The model scalars the brief names; D0's other columns are build diagnostics.
MODEL_SCALARS = ("sigma_atm_front", "sigma_atm_next", "tau_front", "tau_next", "front_fwd", "m0")
HELDOUT_END = pd.Timestamp("2025-01-01")


@dataclass
class Data:
    ev: pd.DataFrame  # keys, dates, block, y, rv, U, l4 columns, half_spread
    inp: d1lib.Inputs
    surf_sha: str
    channel_names: tuple[str, ...]
    scalar_names: tuple[str, ...]


def surfaces_path() -> Path:
    """The surface file named in D0's marker (first token that ends in ``.npz``).

    ``D1_SYNTHETIC_SURFACES`` overrides it for the synthetic dry run only; every real run
    prints the file's sha256, and the frozen scorer checks it.
    """
    import os

    fake = os.environ.get("D1_SYNTHETIC_SURFACES")
    if fake:
        print(f"[surfaces] SYNTHETIC override {fake}")
        return Path(fake)
    if not READY.exists():
        raise FileNotFoundError(f"{READY} missing: D0 has not finished the surfaces")
    for line in READY.read_text(encoding="utf-8").splitlines():
        for tok in line.replace("`", " ").split():
            if tok.endswith(".npz"):
                p = Path(tok)
                return p if p.is_absolute() else ROOT / p
    raise ValueError("SURFACES_READY.txt names no .npz file")


def _features(keys: pd.DataFrame) -> pd.DataFrame:
    """L4's seven 15:59 features, causally standardised exactly as ``l4lib.design`` does."""
    cfg = d1lib.ONLINE_BAYES_L4_MODEL
    p = pd.read_parquet(PANEL, columns=list(dict.fromkeys(KEYS + list(ob.RAW_COLUMNS))))
    p["entry_date"] = pd.to_datetime(p["entry_date"]).dt.normalize()
    m = keys[KEYS].merge(p, on=KEYS, how="left", validate="one_to_one", indicator=True)
    if (m["_merge"] != "both").any():
        raise ValueError(f"{int((m['_merge'] != 'both').sum())} events lack a panel row")
    raw = ob.build_features(m, cfg)
    z, _ = ob.causal_standardise(raw[list(ob.FEATURES)], m["entry_date"], cfg.min_prior_events)
    z["half_spread_raw"] = m["half_spread"].to_numpy(float)
    return z


def _surfaces(keys: pd.DataFrame) -> tuple[np.ndarray, np.ndarray, list[str], list[str], str]:
    path = surfaces_path()
    sha = sha256_file(path)
    f = np.load(path, allow_pickle=False)
    names = list(f.files)
    print(f"[surfaces] {path.name} sha256 {sha[:12]}; arrays {names}")
    tk = f["ticker"].astype(str)
    ed = pd.to_datetime(f["entry_date"]).normalize()
    sk = pd.DataFrame({"ticker": tk, "entry_date": ed, "_i": np.arange(tk.size)})
    m = keys[KEYS].merge(sk, on=KEYS, how="left", validate="one_to_one")
    if m["_i"].isna().any():
        raise ValueError(f"{int(m['_i'].isna().sum())} events have no surface row")
    idx = m["_i"].to_numpy(int)
    surf = np.asarray(f["grid"], float)[idx]
    all_sn = [str(c) for c in f["scalar_names"]]
    miss = [c for c in MODEL_SCALARS if c not in all_sn]
    if miss:
        raise ValueError(f"surface file lacks scalars {miss}")
    scal = np.asarray(f["scalars"], float)[idx][:, [all_sn.index(c) for c in MODEL_SCALARS]]
    ch = [str(c) for c in f["channels"]]
    sn = list(MODEL_SCALARS)
    return surf, scal, ch, sn, sha


def load(mode: str, *, with_2025: bool = False, viewer: str = "D1") -> Data:
    """Assemble every input; ``mode`` is ``"dev"`` or ``"heldout"``."""
    if mode not in ("dev", "heldout"):
        raise ValueError("mode is dev or heldout")
    t = pd.read_parquet(TARGETS)
    for c in ("entry_date", "expiry", "announce_date"):
        t[c] = pd.to_datetime(t[c]).dt.normalize()
    t = t.sort_values(KEYS, kind="stable").reset_index(drop=True)
    stamp = pd.Timestamp.now(tz="UTC").isoformat(timespec="seconds")
    late = t["entry_date"] >= DEV_END
    if mode == "dev":
        t.loc[late, ["H_net", "residual_value", "H_corr"]] = np.nan
        t.loc[late, "target_ok"] = False
        log_block_view(
            BLOCKS_VIEWED,
            panel="D0 targets (base_corrected)",
            period="2013-18",
            outcome_family="H_net_log_density_and_book",
            feature_family="dl_surface_network",
            viewed_by=f"{viewer} dev (loaded {stamp})",
            kind="trial",
        )
    else:
        if not with_2025:
            t.loc[t["entry_date"] >= HELDOUT_END, ["H_net", "residual_value", "H_corr"]] = np.nan
            t.loc[t["entry_date"] >= HELDOUT_END, "target_ok"] = False
        for per in ("2019-24",) + (("2025-26",) if with_2025 else ()):
            log_block_view(
                BLOCKS_VIEWED,
                panel="D0 targets (base_corrected)",
                period=per,
                outcome_family="H_net_log_density_and_book",
                feature_family="dl_surface_network",
                viewed_by=f"{viewer} frozen held-out scorer (loaded {stamp})",
                kind="trial",
            )
    li = pd.read_parquet(L4_INPUTS)
    li["entry_date"] = pd.to_datetime(li["entry_date"]).dt.normalize()
    ev = t.merge(li, on=KEYS, how="left", validate="one_to_one", suffixes=("", "_l4in"))
    ls = pd.read_parquet(L4_SCORES)
    ls["entry_date"] = pd.to_datetime(ls["entry_date"]).dt.normalize()
    if mode == "dev":
        ls = ls[ls["entry_date"] < DEV_END]
    elif not with_2025:
        ls = ls[ls["entry_date"] < HELDOUT_END]
    ev = ev.merge(ls, on=KEYS, how="left", validate="one_to_one", suffixes=("", "_l4sc"))
    for c in (L4_SCORE_MODEL, L4_SCORE_BASE):
        # Only events L4 itself scored (>= 200 settled trades) enter a comparison.
        ev.loc[ev["m_scored"].ne(True), c] = np.nan
    if not np.allclose(ev["U_pct"], ev["U_pct_l4in"], equal_nan=True):
        raise ValueError("U_pct disagrees between targets and l4_inputs")
    feats = _features(ev)
    surf, scal, ch, sn, sha = _surfaces(ev)
    ev["half_spread"] = feats.pop("half_spread_raw").to_numpy()
    pct = d1lib.CFG.pct_per_unit
    ev["y"] = np.where(ev["target_ok"], ev["H_net"] * pct, np.nan)
    ev["rv"] = np.where(ev["target_ok"], ev["residual_value"] * pct, np.nan)
    ev["year"] = ev["entry_date"].dt.year
    z = d1lib.to_z(ev["y"].to_numpy(), ev["U_pct"].to_numpy())
    mask_name = [c for c in ch if "mask" in c.lower() or "valid" in c.lower()]
    if len(mask_name) != 1:
        raise ValueError(f"cannot identify the single mask channel in {ch}")
    inp = d1lib.Inputs(
        surf=surf,
        mask_ch=ch.index(mask_name[0]),
        scal=scal,
        feats=feats[list(ob.FEATURES)].to_numpy(float),
        l4_loc=ev[L4_LOC].to_numpy(float),
        l4_scale=ev[L4_SCALE].to_numpy(float),
        z=z,
        channel_names=tuple(ch),
    )
    print(
        f"[load {mode}] {len(ev)} events; target_ok {int(ev['target_ok'].sum())}; "
        f"L4 loc finite {int(np.isfinite(inp.l4_loc).sum())}; features finite "
        f"{int(np.isfinite(inp.feats).all(axis=1).sum())}; L4 model score finite "
        f"{int(np.isfinite(ev[L4_SCORE_MODEL]).sum())}"
    )
    return Data(ev, inp, sha, tuple(ch), tuple(sn))


# Column names in D0's L4 files, set once those files are read (see STATE.md).
L4_LOC = "m_pred_loc"
L4_SCALE = "m_pred_scale"
L4_SCORE_MODEL = "m_log_score"
L4_SCORE_BASE = "b_log_score"
