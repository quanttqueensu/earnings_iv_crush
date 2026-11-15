"""
addendum.py
Lane D1 addendum, requested by the team lead after D1's held-out reads, so every number it
writes is exploratory. Two mechanism arms:

1. Fill-rate control. D1b with the primary's trunk, no surface grid, and as its only
   additions over L4 the front and next fill rates (D0's ``fill_front``, ``fill_next``) beside
   L4's seven features. Development folds (2 seeds, logged to ``addendum_search_log.csv``, outside
   the 40-configuration search), then a hashed freeze (``freeze_D1_addendum.md``), then one read
   of 2019-24 and one of 2025-26 with the frozen scorer's walk-forward and summary code.
2. Mask occlusion. The frozen primary and secondary are refit on 2019-24 exactly as the frozen
   scorer did (same code, seeds and folds) and predicted with the mask channel zeroed and with
   it set to its training mean per point, beside the three original arms. The refit's own log
   scores are compared with the stored cards as a reproducibility check.

Imports the frozen modules and edits none of them.

Basis: nats per event in H_net space (density per % of m0, Jacobian included); book figures
in % of m0 per trade, net at the touch, not annualised; date-clustered 95%.

Usage
-----
    python .../addendum.py dev
    python .../addendum.py freeze
    python .../addendum.py heldout --block 2019-24
    python .../addendum.py heldout --block 2025-26
    python .../addendum.py mask --which primary
"""

from __future__ import annotations

import argparse
import hashlib
import json
import time
from pathlib import Path
from typing import Any

import d1data
import d1eval
import d1lib
import numpy as np
import pandas as pd
import score_heldout as sh
import search
import torch

HERE = Path(__file__).resolve().parent
LOG = HERE / "addendum_search_log.csv"
FROZEN = HERE / "frozen_addendum.json"
FREEZE = HERE / "freeze_D1_addendum.md"
OUT = HERE / "heldout"
FILL = ("fill_front", "fill_next")


def fill_spec() -> d1lib.ModelSpec:
    """The primary's trunk and head, without the grid."""
    prim = json.loads((HERE / "frozen_config.json").read_text(encoding="utf-8"))["primary"]
    return d1lib.ModelSpec(**{**prim["spec"], "use_surface": False})


def with_fill(D: Any) -> Any:
    """Replace the six surface scalars by the two fill rates (read from D0's file by name)."""
    f = np.load(d1data.surfaces_path(), allow_pickle=False)
    names = [str(c) for c in f["scalar_names"]]
    tk = f["ticker"].astype(str)
    ed = pd.to_datetime(f["entry_date"]).normalize()
    sk = pd.DataFrame({"ticker": tk, "entry_date": ed, "_i": np.arange(tk.size)})
    m = D.ev[d1data.KEYS].merge(sk, on=d1data.KEYS, how="left", validate="one_to_one")
    if m["_i"].isna().any():
        raise ValueError("events without a surface row")
    sc = np.asarray(f["scalars"], float)[m["_i"].to_numpy(int)][:, [names.index(c) for c in FILL]]
    print(
        f"[fill] {FILL}: finite {np.isfinite(sc).all(axis=1).sum()} of {len(sc)}; "
        f"mean {np.nanmean(sc, axis=0).round(3)}"
    )
    D.inp.scal = sc
    D.scalar_names = FILL
    return D


def _sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def hashed() -> dict[str, Path]:
    return {
        "addendum_sha256": Path(__file__).resolve(),
        "d1lib_sha256": HERE / "d1lib.py",
        "d1data_sha256": HERE / "d1data.py",
        "d1eval_sha256": HERE / "d1eval.py",
        "score_heldout_sha256": HERE / "score_heldout.py",
        "search_sha256": HERE / "search.py",
        "frozen_addendum_sha256": FROZEN,
        "addendum_search_log_sha256": LOG,
    }


def verify() -> None:
    raw = FREEZE.read_bytes()
    cut = raw.rfind(b"\nself_sha256: ")
    body, tail = raw[: cut + 1], raw[cut + 1 :].decode().strip()
    if cut < 0 or hashlib.sha256(body).hexdigest() != tail.split(": ", 1)[1]:
        raise ValueError("addendum freeze note changed after it was hashed")
    text = body.decode("utf-8")
    for name, path in hashed().items():
        want = [ln.split(": ", 1)[1] for ln in text.splitlines() if ln.startswith(f"{name}: ")]
        if len(want) != 1 or _sha(path) != want[0].strip():
            raise ValueError(f"{path.name} does not match {name}")
    print("[freeze] addendum verified")


def dev(device: str) -> None:
    if LOG.exists():
        raise SystemExit("addendum_search_log.csv exists; the control is fitted once")
    D = with_fill(d1data.load("dev", viewer="D1 addendum"))
    spec = fill_spec()
    t0 = time.time()
    search.PRED_DIR = HERE / "dev_preds"
    row = {
        "config_id": "fill_control",
        "spec": json.dumps(spec.to_dict()),
        "scalars": "|".join(FILL),
        **search.evaluate(
            spec, D, list(range(d1lib.CFG.n_search_seeds)), device, "addendum_fill_control"
        ),
        "seconds": round(time.time() - t0, 1),
        "utc": pd.Timestamp.now(tz="UTC").isoformat(timespec="seconds"),
    }
    pd.DataFrame([row]).to_csv(LOG, index=False)
    print({k: row[k] for k in row if k.startswith(("gain_l4", "gain_base", "n_scored"))})


def freeze() -> None:
    if FREEZE.exists():
        raise SystemExit("addendum freeze exists")
    surf = json.loads((HERE / "frozen_config.json").read_text(encoding="utf-8"))["surfaces_sha256"]
    FROZEN.write_text(
        json.dumps(
            {
                "fill_control": {"spec": fill_spec().to_dict(), "scalars": list(FILL)},
                "seeds": [0, 1, 2, 3, 4],
                "surfaces_sha256": surf,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    dev_row = pd.read_csv(LOG).iloc[0].to_dict()
    lines = [
        "# Freeze note: lane D1 addendum, fill-rate control",
        "",
        f"Written {pd.Timestamp.now(tz='UTC').isoformat(timespec='seconds')}, after D1's frozen "
        "held-out reads and at the team lead's request; every read under it is exploratory.",
        "",
        "Comparator: D1b with the primary's trunk, no grid, and only the front and next fill "
        "rates added to L4's seven features. Development (2 seeds): "
        + ", ".join(f"{k} {dev_row[k]}" for k in dev_row if k.startswith("gain_l4")),
        "",
        "Reading, declared now: if D1b's held-out gain over L4 is not clearly larger than this "
        "control's (the primary-minus-control difference has a lower bound above zero), the "
        "chain's information is reported as how sparse the chain is, a liquidity measure.",
        "",
        "## Hashes",
        "",
    ] + [f"{k}: {_sha(v)}" for k, v in hashed().items()]
    body = ("\n".join(lines) + "\n").encode("utf-8")
    FREEZE.write_bytes(body + f"self_sha256: {hashlib.sha256(body).hexdigest()}\n".encode())
    print(FREEZE.read_text(encoding="utf-8"))


def heldout(block: str, device: str) -> None:
    verify()
    fz = json.loads(FROZEN.read_text(encoding="utf-8"))
    res_path = OUT / f"results_fill_control_{block}.json"
    if res_path.exists():
        raise SystemExit(f"{res_path.name} exists: read once already")
    D = with_fill(
        d1data.load("heldout", with_2025=(block == "2025-26"), viewer="D1 addendum fill_control")
    )
    if D.surf_sha != fz["surfaces_sha256"]:
        raise ValueError("surface file changed")
    spec = d1lib.ModelSpec(**fz["fill_control"]["spec"])
    lo, hi = sh.BLOCKS[block]
    folds = d1eval.quarter_folds(D, lo, hi, d1lib.CFG.val_days)
    partial = OUT / f"cards_fill_control_{block}.partial.parquet"
    cards = sh.walk_forward(spec, D, folds, fz["seeds"], device, {}, partial)
    cards = cards[cards["block"] == block].reset_index(drop=True)
    cards.to_parquet(OUT / f"cards_fill_control_{block}.parquet")
    partial.unlink(missing_ok=True)
    res = sh.summarise(cards, spec, block)
    prim = pd.read_parquet(OUT / f"cards_primary_{block}.parquet")
    m = prim[d1data.KEYS + ["log_score", "announce_date", "year"]].merge(
        cards[d1data.KEYS + ["log_score"]],
        on=d1data.KEYS,
        validate="one_to_one",
        suffixes=("", "_fill"),
    )
    if len(m) != len(prim):
        raise ValueError("cards do not match one to one")
    res["primary_minus_fill_control"] = d1eval.log_score_gain(
        m["log_score"].to_numpy(),
        m["log_score_fill"].to_numpy(),
        m["announce_date"].to_numpy(),
        m["year"].to_numpy(),
    )
    res["label"] = "EXPLORATORY: comparator added after D1's held-out reads"
    res_path.write_text(json.dumps(res, indent=2, default=str) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {k: res[k] for k in ("vs_L4_model", "primary_minus_fill_control")},
            indent=1,
            default=str,
        )
    )


def _predict_mask_mean(
    fr: d1lib.FitResult, D: Any, rows: np.ndarray, train: np.ndarray, device: str
) -> d1lib.Predictive:
    """Ensemble predictive with the mask channel replaced by its training mean per point."""
    mc = D.inp.mask_ch
    mean_mask = (D.inp.surf[train][:, mc] > 0.5).mean(axis=0).astype(np.float32)
    preds = []
    for net, nrm in zip(fr.nets, fr.nrms, strict=True):
        sn, side = nrm.apply(D.inp, rows)
        sn[:, mc] = mean_mask
        loc = np.nan_to_num(D.inp.l4_loc[rows], nan=0.0)
        ls = np.log(np.where(np.isfinite(D.inp.l4_scale[rows]), D.inp.l4_scale[rows], 1.0))
        t = [torch.as_tensor(a, dtype=torch.float32, device=device) for a in (sn, side, loc, ls)]
        net.eval()
        with torch.no_grad():
            logw, mu, sig, df = net(*t)
        to = lambda x: x.detach().cpu().double().numpy()  # noqa: E731
        preds.append(
            d1lib.Predictive(np.exp(to(logw)), to(mu), to(sig), None if df is None else to(df))
        )
    return d1lib.ensemble(preds)


def mask(which: str, device: str) -> None:
    res_path = OUT / f"mask_occlusion_{which}_2019-24.json"
    if res_path.exists():
        raise SystemExit(f"{res_path.name} exists")
    sh.verify_freeze()
    fz = json.loads((HERE / "frozen_config.json").read_text(encoding="utf-8"))
    spec = d1lib.ModelSpec(**fz[which]["spec"])
    D = d1data.load("heldout", viewer=f"D1 addendum mask occlusion refit {which}")
    folds = d1eval.quarter_folds(D, *sh.BLOCKS["2019-24"], d1lib.CFG.val_days)
    occl = sh.occlusion_channels(D.channel_names, D.inp.mask_ch)
    arms = {**occl, "mask_zero": (D.inp.mask_ch,)}
    y_all, u_all = D.ev["y"].to_numpy(), D.ev["U_pct"].to_numpy()
    frames = []
    for f in folds:
        fr = d1lib.fit_two_stage(spec, D.inp, f.train, f.val, fz["seeds"], device)
        y, u = y_all[f.score], u_all[f.score]
        e = D.ev.iloc[f.score][d1data.KEYS + ["announce_date", "year"]].copy()
        e["log_score"] = d1lib.score_rows(d1lib.predict_ensemble(fr, D.inp, f.score, device), y, u)[
            "log_score"
        ]
        for g, chs in arms.items():
            e[f"ls_{g}"] = d1lib.logscore_y(
                y, u, d1lib.predict_ensemble(fr, D.inp, f.score, device, occlude=chs)
            )
        e["ls_mask_mean"] = d1lib.logscore_y(
            y, u, _predict_mask_mean(fr, D, f.score, f.train, device)
        )
        frames.append(e)
        print(f"[mask] {which} {f.origin.date()} done", flush=True)
    c = pd.concat(frames, ignore_index=True)
    stored = pd.read_parquet(OUT / f"cards_{which}_2019-24.parquet")
    m = c.merge(
        stored[d1data.KEYS + ["log_score"]],
        on=d1data.KEYS,
        validate="one_to_one",
        suffixes=("", "_stored"),
    )
    diff = (m["log_score"] - m["log_score_stored"]).to_numpy()
    cl = m["announce_date"].to_numpy()
    out: dict[str, Any] = {
        "label": "EXPLORATORY: refit after the held-out read",
        "N": len(m),
        "reproducibility_vs_stored_cards": {
            "max_abs": float(np.max(np.abs(diff))),
            "mean": float(np.mean(diff)),
        },
    }
    for k in [c_ for c_ in m.columns if c_.startswith("ls_")]:
        out[f"change_{k[3:]}"] = d1eval._iv(
            d1eval.date_clustered_ci((m[k] - m["log_score"]).to_numpy(), cl, np.mean), 5
        )
    res_path.write_text(json.dumps(out, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(out, indent=1))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", choices=["dev", "freeze", "heldout", "mask"])
    ap.add_argument("--block", choices=list(sh.BLOCKS), default="2019-24")
    ap.add_argument("--which", choices=["primary", "secondary"], default="primary")
    ap.add_argument("--device", default="cuda" if torch.cuda.is_available() else "cpu")
    a = ap.parse_args()
    if a.mode == "dev":
        dev(a.device)
    elif a.mode == "freeze":
        freeze()
    elif a.mode == "heldout":
        heldout(a.block, a.device)
    else:
        mask(a.which, a.device)


if __name__ == "__main__":
    main()
