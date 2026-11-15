"""
test_online_bayes.py
Offline tests of the sequential normal-inverse-gamma model in
``earnings_iv_crush/research/online_bayes.py``, on synthetic data only.

The sequential posterior is checked against the batch conjugate posterior and, in the flat-prior
limit, against statsmodels OLS (an independent implementation). A planted effect must be
recovered, the name intercept must reproduce the empirical-Bayes shrinkage factor, and no trade
may enter the posterior before its expiry: the leak test perturbs every outcome not yet known at
a cut date and requires the predictions up to that date to be unchanged.
"""

from __future__ import annotations

import subprocess
import sys
from dataclasses import asdict
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from earnings_iv_crush.research import online_bayes as ob

# ── synthetic book ───────────────────────────────────────────────────────────


def _book(
    n_dates: int = 120,
    per_date: int = 6,
    n_names: int = 25,
    beta: tuple[float, ...] = (0.5, 1.0, -0.5),
    name_sd: float = 0.0,
    noise: float = 1.0,
    seed: int = 0,
) -> tuple[pd.DataFrame, np.ndarray, np.ndarray]:
    """Events on business days, settling 1 to 10 business days later, some on entry dates."""
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range("2014-01-02", periods=n_dates)
    entry = np.repeat(dates, per_date)
    n = entry.size
    hold = rng.integers(1, 11, n)
    settle = entry + pd.to_timedelta(hold, unit="D")
    names = rng.integers(0, n_names, n).astype(str)
    p = len(beta)
    X = np.column_stack([np.ones(n), rng.standard_normal((n, p - 1))])
    u = rng.normal(0.0, name_sd, n_names) if name_sd > 0 else np.zeros(n_names)
    y = X @ np.asarray(beta) + u[names.astype(int)] + rng.normal(0.0, noise, n)
    frame = pd.DataFrame(
        {
            "entry_date": entry,
            "settle_date": settle,
            "name": names,
            "cluster": entry,
            "y": y,
            "v": 1.0,
        }
    )
    return frame, X, u


def _cfg(**kw: float | str) -> ob.OnlineBayesConfig:
    base: dict[str, float | str | int] = dict(
        discount=1.0,
        coef_prior_scale=1.0,
        intercept_prior_scale=1.0,
        name_prior_scale=0.0,
        prior_df=2.0,
        prior_sigma=1.0,
        variance_weight="none",
        min_settled=50,
    )
    base.update(kw)
    return ob.OnlineBayesConfig(**base)  # type: ignore[arg-type]


# ── conjugacy ────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("n,p,seed", [(30, 2, 0), (200, 4, 1), (500, 6, 2)])
@pytest.mark.parametrize("weighted", [False, True])
def test_sequential_equals_batch_without_names(n: int, p: int, seed: int, weighted: bool) -> None:
    rng = np.random.default_rng(seed)
    X = np.column_stack([np.ones(n), rng.standard_normal((n, p - 1))])
    y = X @ rng.standard_normal(p) + rng.standard_normal(n)
    v = rng.uniform(0.3, 3.0, n) if weighted else np.ones(n)
    cfg = _cfg(coef_prior_scale=0.5, intercept_prior_scale=2.0, prior_sigma=1.7, prior_df=3.0)
    st = ob.NIGState.prior(p, cfg)
    m0, C0, a0, b0 = st.m.copy(), st.C.copy(), st.a, st.b
    for i in range(n):
        st.update(X[i], "x", y[i], v[i])
    m, C, a, b = ob.batch_posterior(X, y, v, m0, C0, a0, b0)
    np.testing.assert_allclose(st.m, m, rtol=1e-9, atol=1e-10)
    np.testing.assert_allclose(st.C, C, rtol=1e-8, atol=1e-12)
    assert st.a == pytest.approx(a)
    assert st.b == pytest.approx(b, rel=1e-9)


@pytest.mark.parametrize("kappa", [0.01, 0.3, 2.0])
def test_sequential_equals_batch_with_names(kappa: float) -> None:
    frame, X, _ = _book(n_dates=40, per_date=5, n_names=8, name_sd=0.7, seed=3)
    cfg = _cfg(name_prior_scale=kappa, coef_prior_scale=0.4)
    p = X.shape[1]
    st = ob.NIGState.prior(p, cfg)
    C0p, a0, b0 = st.C.copy(), st.a, st.b
    names = frame["name"].to_numpy()
    for i in range(len(frame)):
        st.update(X[i], names[i], frame["y"].iloc[i], 1.0)
    order = sorted(st.names, key=lambda k: st.names[k])
    D = np.zeros((len(frame), len(order)))
    for j, nm in enumerate(order):
        D[:, j] = names == nm
    F = np.hstack([X, D])
    k = len(order)
    C0 = np.zeros((p + k, p + k))
    C0[:p, :p] = C0p
    C0[p:, p:] = kappa * np.eye(k)
    m, C, a, b = ob.batch_posterior(
        F, frame["y"].to_numpy(), np.ones(len(frame)), np.zeros(p + k), C0, a0, b0
    )
    np.testing.assert_allclose(st.m, m, rtol=1e-8, atol=1e-10)
    np.testing.assert_allclose(st.C, C, rtol=1e-7, atol=1e-11)
    assert st.b == pytest.approx(b, rel=1e-9)


def test_flat_prior_matches_statsmodels_ols() -> None:
    sm = pytest.importorskip("statsmodels.api")
    rng = np.random.default_rng(7)
    n, p = 400, 5
    X = np.column_stack([np.ones(n), rng.standard_normal((n, p - 1))])
    y = X @ np.array([0.3, -1.0, 0.5, 2.0, 0.0]) + rng.standard_normal(n) * 1.3
    # Reference prior: C0 -> infinity, a0 = -p / 2, b0 = 0 (West and Harrison's n0 = -p).
    st = ob.NIGState(p, np.zeros(p), 1e8 * np.eye(p), -p / 2.0, 0.0, 0.0)
    for i in range(n):
        st.update(X[i], "x", y[i], 1.0)
    fit = sm.OLS(y, X).fit()
    s2 = st.b / st.a
    np.testing.assert_allclose(st.m, fit.params, rtol=1e-5, atol=1e-7)
    assert s2 == pytest.approx(fit.scale, rel=1e-5)
    np.testing.assert_allclose(s2 * st.C, fit.cov_params(), rtol=1e-4, atol=1e-9)


# ── recovery ─────────────────────────────────────────────────────────────────


def test_planted_effect_is_recovered_and_scores_above_baseline() -> None:
    beta = (0.4, 0.8, -0.6)
    frame, X, _ = _book(n_dates=300, per_date=8, beta=beta, noise=1.5, seed=11)
    cfg = _cfg(coef_prior_scale=0.1)
    run = ob.run_online(frame, X, cfg, coef_names=["c", "x1", "x2"], quiet=True)
    loc = run.state.m[:3]
    sd = np.sqrt(run.state.b / run.state.a * np.diag(run.state.C)[:3])
    assert np.all(np.abs(loc - np.array(beta)) < 4 * sd)
    base = ob.run_online(frame, X[:, :1], cfg, coef_names=["c"], quiet=True)
    s = run.events["scored"] & base.events["scored"]
    gain = (run.events.loc[s, "log_score"] - base.events.loc[s, "log_score"]).mean()
    assert gain > 0.05
    # On a correctly specified book the 90% predictive interval covers about 90%.
    assert run.events.loc[s, "covered"].mean() == pytest.approx(0.90, abs=0.03)


def test_name_effect_reproduces_empirical_bayes_shrinkage() -> None:
    # Intercept pinned at zero and no features: the name intercept's posterior mean is
    # B * mean with B = kappa / (kappa + 1 / n), i.e. tau^2 / (tau^2 + sigma^2 / n).
    kappa = 0.2
    cfg = _cfg(name_prior_scale=kappa, intercept_prior_scale=1e-14)
    st = ob.NIGState.prior(1, cfg)
    rng = np.random.default_rng(5)
    obs = {
        nm: rng.normal(mu, 1.0, k) for nm, mu, k in [("A", 1.0, 3), ("B", -2.0, 12), ("C", 0.5, 1)]
    }
    for nm, vals in obs.items():
        for yv in vals:
            st.update(np.array([1.0]), nm, yv, 1.0)
    for nm, vals in obs.items():
        k = vals.size
        shrink = kappa / (kappa + 1.0 / k)
        assert st.name_effect(nm) == pytest.approx(shrink * vals.mean(), rel=1e-6)


def test_planted_name_effect_is_recovered() -> None:
    frame, X, u = _book(n_dates=250, per_date=8, n_names=20, name_sd=1.0, noise=1.0, seed=4)
    run = ob.run_online(
        frame, X, _cfg(name_prior_scale=1.0), coef_names=["c", "a", "b"], quiet=True
    )
    est = np.array([run.state.name_effect(str(k)) for k in range(u.size)])
    # The intercept absorbs the names' mean, so compare demeaned effects.
    assert np.corrcoef(est, u - u.mean())[0, 1] > 0.9


def test_discount_tracks_a_break() -> None:
    rng = np.random.default_rng(9)
    frame, X, _ = _book(n_dates=400, per_date=4, beta=(0.0, 1.0), seed=9)
    half = frame["entry_date"] >= frame["entry_date"].iloc[len(frame) // 2]
    frame["y"] = np.where(half, -1.0, 1.0) * X[:, 1] + rng.standard_normal(len(frame))
    fixed = ob.run_online(frame, X, _cfg(), coef_names=["c", "x"], quiet=True)
    fast = ob.run_online(frame, X, _cfg(discount=0.98), coef_names=["c", "x"], quiet=True)
    assert abs(fast.state.m[1] + 1.0) < abs(fixed.state.m[1] + 1.0)
    assert abs(fast.state.m[1] + 1.0) < 0.3


# ── causality ────────────────────────────────────────────────────────────────


def test_no_trade_enters_before_its_expiry() -> None:
    frame, X, _ = _book(seed=21)
    run = ob.run_online(frame, X, _cfg(), coef_names=["c", "a", "b"], quiet=True)
    upd = run.events["update_date"]
    settle = pd.to_datetime(frame["settle_date"])
    dates = np.sort(frame["entry_date"].unique())
    inside = settle.to_numpy() < dates[-1]
    # Trades settling on or after the last entry date have no later date to enter on.
    assert upd[inside].notna().all() and upd[~inside].isna().all()
    assert (upd[inside] > settle[inside]).all()
    # It enters on the first entry date strictly after expiry, not later.
    nxt = dates[np.searchsorted(dates, settle.to_numpy(), side="right").clip(max=dates.size - 1)]
    assert (upd.to_numpy()[inside] == nxt[inside]).all()
    # Some trades settle exactly on an entry date, so a <= rule would differ from <.
    assert frame["settle_date"].isin(frame["entry_date"]).any()


def test_predictions_ignore_outcomes_not_yet_known() -> None:
    frame, X, _ = _book(seed=22, name_sd=0.5)
    cfg = _cfg(name_prior_scale=0.2, discount=0.99)
    cut = frame["entry_date"].unique()[70]
    unknown = frame["settle_date"] >= cut  # not settled strictly before the cut date
    leaked = frame.copy()
    leaked.loc[unknown, "y"] = leaked.loc[unknown, "y"] + 1e3
    a = ob.run_online(frame, X, cfg, coef_names=["c", "a", "b"], quiet=True).events
    b = ob.run_online(leaked, X, cfg, coef_names=["c", "a", "b"], quiet=True).events
    upto = frame["entry_date"] <= cut
    for col in ("pred_loc", "pred_scale", "p_pos"):
        np.testing.assert_array_equal(a.loc[upto, col].to_numpy(), b.loc[upto, col].to_numpy())
    later = frame["entry_date"] > frame.loc[unknown, "settle_date"].min()
    assert not np.allclose(a.loc[later, "pred_loc"], b.loc[later, "pred_loc"])


def test_settle_on_or_before_entry_raises() -> None:
    frame, X, _ = _book(n_dates=10, seed=1)
    frame.loc[0, "settle_date"] = frame.loc[0, "entry_date"]
    with pytest.raises(ValueError, match="settle on or before entry"):
        ob.run_online(frame, X, _cfg(), coef_names=["c", "a", "b"], quiet=True)


def test_causal_standardise_uses_strictly_earlier_dates() -> None:
    rng = np.random.default_rng(2)
    dates = pd.Series(np.repeat(pd.bdate_range("2015-01-01", periods=30), 4))
    raw = pd.DataFrame({"a": rng.standard_normal(dates.size), "b": rng.standard_normal(dates.size)})
    raw.loc[5, "b"] = np.nan
    z, n_prior = ob.causal_standardise(raw, dates, min_prior=8)
    for i in rng.choice(dates.size, 20, replace=False):
        prior = dates < dates[i]
        assert n_prior[i] == int(prior.sum())
        if prior.sum() < 8:
            assert z.iloc[i].isna().all()
            continue
        for c in ("a", "b"):
            ref = raw.loc[prior, c].dropna()
            val = raw.loc[i, c]
            want = 0.0 if np.isnan(val) else (val - ref.mean()) / ref.std(ddof=1)
            assert z.loc[i, c] == pytest.approx(want)


def test_variance_weight_is_causal() -> None:
    dates = pd.Series(np.repeat(pd.bdate_range("2015-01-01", periods=5), 2))
    ps = np.array([1.0, 1.0, 2.0, 2.0, 1.0, 3.0, 1.0, 1.0, 2.0, 2.0])
    v = ob.causal_variance_weight(ps, dates, "premium_share", min_prior=2)
    assert np.isnan(v[:2]).all()
    assert v[2] == pytest.approx(4.0 / 1.0)
    assert v[4] == pytest.approx(1.0 / 2.5)
    assert np.all(ob.causal_variance_weight(ps, dates, "none", 2) == 1.0)


# ── scoring helpers ──────────────────────────────────────────────────────────


def test_date_stratified_null_matches_per_date_counts() -> None:
    dates = np.repeat(pd.bdate_range("2016-01-01", periods=10), 5)
    y = np.repeat(np.arange(10.0), 5)  # constant within a date
    sel = np.zeros(50, bool)
    sel[[0, 1, 7, 20, 21, 22, 49]] = True
    res = ob.date_stratified_null(y, sel, dates, n_draws=200, seed=0)
    assert res.observed == pytest.approx(y[sel].mean())
    np.testing.assert_allclose(res.null, y[sel].mean())


def test_kish_design_effect_detects_clustering() -> None:
    rng = np.random.default_rng(3)
    g = np.repeat(np.arange(200), 10)
    for shock, lo, hi in [(0.0, 0.8, 1.3), (1.0, 3.0, 9.0)]:
        z = rng.normal(0.0, shock, 200)[g] + rng.standard_normal(g.size)
        cnt = np.bincount(g).astype(float)
        s1 = np.bincount(g, weights=z)
        s2 = np.bincount(g, weights=z * z)
        _, deff = ob._kish_deff(cnt, s1, s2)
        assert lo <= deff <= hi


def test_grid_is_the_declared_search_space() -> None:
    cfg = ob.OnlineBayesConfig()
    full = ob.grid(cfg, with_features=True)
    base = ob.grid(cfg, with_features=False)
    n_dwu = len(cfg.discount_grid) * len(cfg.name_prior_grid) * len(cfg.variance_weight_grid)
    assert len(full) == n_dwu * len(cfg.coef_prior_grid)
    assert len(base) == n_dwu
    assert len({tuple(ob.describe_config(c).values()) for c in full}) == len(full)


# ── forward mode ─────────────────────────────────────────────────────────────


def test_forward_with_no_trades_prints_n0_and_exits_nonzero(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code = ob.forward_update(None, root=tmp_path)
    assert code != 0
    assert "N=0" in capsys.readouterr().out


def test_forward_updates_on_fake_settled_trades(tmp_path: Path) -> None:
    keys = pd.DataFrame(
        {"ticker": ["AAA", "BBB"], "entry_date": pd.to_datetime(["2026-12-01", "2026-12-02"])}
    )
    keys.to_parquet(tmp_path / "forward_ledger_nostop.parquet")
    keys.assign(transmitted=True).to_parquet(tmp_path / "open_positions.parquet")
    keys.assign(assumed_mid_mark_ps=1.0, nostop_fill_ps=1.0).to_parquet(
        tmp_path / "forward_reconciliation.parquet"
    )
    keys.assign(
        expiry=pd.to_datetime(["2026-12-04", "2026-12-05"]), status="ok", H_shadow=[0.01, -0.02]
    ).to_csv(tmp_path / "shadow_book.csv", index=False)
    keys.assign(
        half_spread=0.05,
        implied_move=0.06,
        iv_term_spread=0.3,
        depth_tot=100.0,
        dte=3.0,
        m0=25.0,
        s0=4.0,
    ).to_parquet(tmp_path / "features.parquet")
    cfg = ob.OnlineBayesConfig()
    p = 1 + len(ob.FEATURES)
    st = ob.NIGState.prior(p, cfg)
    meta = {
        "config": asdict(cfg),
        "feature_mean": [0.0] * len(ob.FEATURES),
        "feature_sd": [1.0] * len(ob.FEATURES),
        "premium_share_sq_mean": 0.03,
    }
    st.to_npz(tmp_path / "posterior.npz", meta)
    out = tmp_path / "posterior_after.npz"
    code = ob.forward_update(
        tmp_path / "posterior.npz",
        features_path=tmp_path / "features.parquet",
        root=tmp_path,
        out_path=out,
    )
    assert code == 0
    st2, meta2 = ob.NIGState.from_npz(out)
    assert meta2["forward_n"] == 2
    assert st2.a == pytest.approx(st.a + 1.0)


def test_forward_store_paths_mirror_session_stores() -> None:
    # session.py is read as text, never imported: it pulls in the order modules.
    src = Path(ob.__file__).resolve().parents[1] / "live" / "session.py"
    text = src.read_text(encoding="utf-8")
    for needle in (
        "open_positions=config.open_positions_path",
        "nostop=FORWARD.nostop_ledger_path",
        "reconciliation=FORWARD.reconciliation_path",
        "dry = Path(config.dry_dir)",
    ):
        assert needle in text, f"Stores.for_mode changed: {needle!r} not found; update the mirror"
    live = ob.forward_store_paths(dry=False)
    dry = ob.forward_store_paths(dry=True)
    assert all(Path(dry[k]).name == Path(live[k]).name for k in live)


def test_forward_path_never_imports_the_order_modules(tmp_path: Path) -> None:
    code = (
        "import sys\n"
        "from earnings_iv_crush.research import online_bayes as ob\n"
        f"ob.forward_update(None, root=r'{tmp_path}')\n"
        "bad = [m for m in sys.modules if m.split('.')[-1] in "
        "('ib_orders', 'ib_market', 'ib_connection', 'session', 'paper_book', 'ladder')"
        " and m.startswith('earnings_iv_crush')]\n"
        "assert not bad, bad\n"
        "assert 'ib_async' not in sys.modules and 'ib_insync' not in sys.modules\n"
    )
    root = Path(ob.__file__).resolve().parents[2]
    res = subprocess.run(
        [sys.executable, "-c", code], cwd=root, capture_output=True, text=True, timeout=120
    )
    assert res.returncode == 0, res.stderr


# ── iteration round: Student-t scale mixture, industry level, variance power, wide set ──


def _grouped_book(
    n_groups: int = 6,
    names_per: int = 5,
    group_sd: float = 1.0,
    seed: int = 11,
    n_dates: int = 120,
    per_date: int = 6,
) -> tuple[pd.DataFrame, np.ndarray, np.ndarray]:
    frame, X, _ = _book(n_dates=n_dates, per_date=per_date, n_names=n_groups * names_per, seed=seed)
    rng = np.random.default_rng(seed + 1)
    w = rng.normal(0.0, group_sd, n_groups)
    gid = frame["name"].astype(int).to_numpy() // names_per
    frame["group"] = [f"g{g}" for g in gid]
    frame["y"] = frame["y"] + w[gid]
    return frame, X, w


def test_new_fields_default_to_the_original_model() -> None:
    frame, X, _ = _book(n_dates=60, name_sd=0.5, seed=4)
    cfg = _cfg(name_prior_scale=0.1)
    a = ob.run_online(frame, X, cfg, coef_names=["c", "a", "b"], quiet=True)
    # A group column is present but the level is off: nothing may change.
    b = ob.run_online(frame.assign(group="g0"), X, cfg, coef_names=["c", "a", "b"], quiet=True)
    for col in ("pred_loc", "pred_scale", "p_pos", "log_score", "pit", "covered"):
        np.testing.assert_array_equal(a.events[col].to_numpy(), b.events[col].to_numpy())
    np.testing.assert_array_equal(a.state.m, b.state.m)


@pytest.mark.parametrize("nu", [2.5, 4.0, 10.0, 150.0])
def test_mixture_predictive_matches_adaptive_quadrature(nu: float) -> None:
    from scipy.integrate import quad
    from scipy.stats import gamma
    from scipy.stats import t as student_t

    cfg = _cfg(obs_df=nu)
    cases = [(0.3, -0.2, 0.05, 1.3, 2.0, 9.0), (-7.0, 0.1, 0.02, 0.7, 4.0, 40.0)]
    for y, loc, q, v, s2, df in cases:
        mp = ob.mixture_predictive(
            np.array([y]),
            np.array([loc]),
            np.array([q]),
            np.array([v]),
            np.array([s2]),
            np.array([df]),
            cfg,
        )

        def comp(
            lam: float,
            kind: str,
            at: float,
            loc: float = loc,
            q: float = q,
            v: float = v,
            s2: float = s2,
            df: float = df,
        ) -> float:
            sc = np.sqrt(s2 * (q + v / lam))
            g = gamma.pdf(lam, nu / 2, scale=2 / nu)
            if kind == "pdf":
                return float(student_t.pdf(at, df, loc=loc, scale=sc) * g)
            return float(student_t.cdf(at, df, loc=loc, scale=sc) * g)

        dens = quad(comp, 0, np.inf, args=("pdf", y), limit=400)[0]
        cdf = quad(comp, 0, np.inf, args=("cdf", y), limit=400)[0]
        ppos = 1.0 - quad(comp, 0, np.inf, args=("cdf", 0.0), limit=400)[0]
        assert mp["log_score"][0] == pytest.approx(np.log(dens), abs=1e-6)
        assert mp["pit"][0] == pytest.approx(cdf, abs=1e-7)
        assert mp["p_pos"][0] == pytest.approx(ppos, abs=1e-7)


def _mp(ys: np.ndarray, cfg: ob.OnlineBayesConfig) -> dict[str, np.ndarray]:
    one = np.ones_like(ys)
    return ob.mixture_predictive(ys, 0.5 * one, 0.04 * one, one, 2.0 * one, 30.0 * one, cfg)


def test_mixture_density_integrates_to_one_and_tends_to_gaussian() -> None:
    ys = np.linspace(-400, 400, 160_001)
    dens = np.exp(_mp(ys, _cfg(obs_df=3.0))["log_score"])
    assert float(np.sum((dens[1:] + dens[:-1]) / 2 * np.diff(ys))) == pytest.approx(1.0, abs=2e-3)
    near = np.linspace(-6, 6, 41)
    gau = _mp(near, _cfg())["log_score"]
    gap_150 = np.abs(_mp(near, _cfg(obs_df=150.0))["log_score"] - gau).max()
    gap_4 = np.abs(_mp(near, _cfg(obs_df=4.0))["log_score"] - gau).max()
    assert gap_150 < 0.1 * gap_4
    with pytest.raises(ValueError, match="obs_df"):
        _mp(near, _cfg(obs_df=1e7))


def test_posterior_lambda_downweights_tail_residuals() -> None:
    cfg = _cfg(obs_df=4.0)
    # With sigma^2 all but known (df 1e4), E[lambda | e] = (nu + 1) / (nu + e^2 / var).
    centre = ob.posterior_lambda(0.0, 0.0, 1.0, 1.0, 1e4, cfg)
    tail = ob.posterior_lambda(8.0, 0.0, 1.0, 1.0, 1e4, cfg)
    assert centre == pytest.approx(5.0 / 4.0, rel=2e-3)
    assert tail == pytest.approx(5.0 / (4.0 + 64.0), rel=2e-3)
    assert ob.posterior_lambda(8.0, 0.0, 1.0, 1.0, 1e4, _cfg()) == 1.0


def test_group_level_equals_batch_posterior() -> None:
    frame, X, _ = _grouped_book(n_groups=3, names_per=3, n_dates=30, per_date=4)
    ku, kg = 0.2, 0.5
    cfg = _cfg(name_prior_scale=ku, group_prior_scale=kg, coef_prior_scale=0.4)
    p = X.shape[1]
    st = ob.NIGState.prior(p, cfg)
    C0p, a0, b0 = st.C.copy(), st.a, st.b
    names, groups = frame["name"].to_numpy(), frame["group"].to_numpy()
    for i in range(len(frame)):
        st.update(X[i], names[i], frame["y"].iloc[i], 1.0, groups[i])
    order = sorted(
        [("n", k, i) for k, i in st.names.items()] + [("g", k, i) for k, i in st.groups.items()],
        key=lambda t: t[2],
    )
    D = np.column_stack([(names if kind == "n" else groups) == k for kind, k, _ in order])
    F = np.hstack([X, D.astype(float)])
    C0 = np.zeros((F.shape[1], F.shape[1]))
    C0[:p, :p] = C0p
    for j, (kind, _, _) in enumerate(order):
        C0[p + j, p + j] = ku if kind == "n" else kg
    m, _, _, b = ob.batch_posterior(
        F, frame["y"].to_numpy(), np.ones(len(frame)), np.zeros(F.shape[1]), C0, a0, b0
    )
    np.testing.assert_allclose(st.m, m, rtol=1e-7, atol=1e-9)
    assert st.b == pytest.approx(b, rel=1e-9)


def test_group_level_recovers_planted_industry_effects() -> None:
    frame, X, w = _grouped_book(n_groups=8, names_per=6, group_sd=1.0, n_dates=200, per_date=6)
    kw: dict[str, float] = dict(name_prior_scale=0.05, intercept_prior_scale=0.01)
    run = ob.run_online(
        frame, X, _cfg(group_prior_scale=1.0, **kw), coef_names=["c", "a", "b"], quiet=True
    )
    est = np.array([run.state.group_effect(f"g{g}") for g in range(8)])
    assert np.corrcoef(est, w)[0, 1] > 0.95
    no_g = ob.run_online(frame, X, _cfg(**kw), coef_names=["c", "a", "b"], quiet=True).events
    sc = run.events["scored"]
    assert run.events.loc[sc, "log_score"].mean() > no_g.loc[sc, "log_score"].mean()


def test_student_t_likelihood_wins_on_gap_tails() -> None:
    frame, X, _ = _book(n_dates=200, per_date=6, seed=21)
    rng = np.random.default_rng(22)
    frame["y"] = X @ np.array([0.5, 1.0, -0.5]) + rng.standard_t(2.5, len(frame))
    gau = ob.run_online(frame, X, _cfg(), coef_names=["c", "a", "b"], quiet=True)
    stu = ob.run_online(frame, X, _cfg(obs_df=2.5), coef_names=["c", "a", "b"], quiet=True)
    sc = gau.events["scored"]
    assert stu.events.loc[sc, "log_score"].mean() > gau.events.loc[sc, "log_score"].mean() + 0.05
    truth = np.array([0.5, 1.0, -0.5])
    assert np.abs(stu.state.m[:3] - truth).max() < np.abs(gau.state.m[:3] - truth).max()
    assert 0.86 < stu.events.loc[sc, "covered"].mean() < 0.94
    assert (stu.events["lambda_hat"].dropna() > 0).all()


def test_leak_check_holds_for_mixture_and_groups() -> None:
    frame, X, _ = _grouped_book(n_dates=100, per_date=5)
    cfg = _cfg(name_prior_scale=0.1, group_prior_scale=0.3, obs_df=4.0, discount=0.99)
    cut = frame["entry_date"].unique()[60]
    unknown = frame["settle_date"] >= cut
    leaked = frame.copy()
    leaked.loc[unknown, "y"] += 1e3
    a = ob.run_online(frame, X, cfg, coef_names=["c", "a", "b"], quiet=True).events
    b = ob.run_online(leaked, X, cfg, coef_names=["c", "a", "b"], quiet=True).events
    upto = frame["entry_date"] <= cut
    for col in ("pred_loc", "pred_scale", "p_pos"):
        np.testing.assert_array_equal(a.loc[upto, col].to_numpy(), b.loc[upto, col].to_numpy())


@pytest.mark.parametrize("power", [1.0, 2.0, 3.0])
def test_variance_power(power: float) -> None:
    dates = pd.Series(np.repeat(pd.bdate_range("2015-01-01", periods=5), 2))
    ps = np.array([1.0, 1.0, 2.0, 2.0, 1.0, 3.0, 1.0, 1.0, 2.0, 2.0])
    v = ob.causal_variance_weight(ps, dates, "premium_share", 2, power=power)
    assert v[4] == pytest.approx(1.0 / ((1.0 + 2.0**power) / 2))
    if power == 2.0:
        np.testing.assert_array_equal(v, ob.causal_variance_weight(ps, dates, "premium_share", 2))


def test_wide_feature_set_columns_and_domain() -> None:
    rng = np.random.default_rng(5)
    n = 50
    panel = pd.DataFrame(
        {
            "ticker": ["A"] * n,
            "half_spread": rng.uniform(0.01, 0.2, n),
            "implied_move": rng.uniform(0.02, 0.1, n),
            "iv_term_spread": rng.normal(0.3, 0.2, n),
            "depth_tot": rng.integers(4, 500, n).astype(float),
            "dte": rng.integers(0, 30, n).astype(float),
            "m0": 30.0,
            "s0": 3.0,
        }
    )
    for _, col, how in ob.WIDE_EXTRA:
        if col not in panel:
            panel[col] = rng.uniform(0.1, 1.0, n) if how != "raw" else rng.normal(0, 1, n)
    panel.loc[3, "wing_spread"] = np.nan
    out = ob.build_feature_set(panel, _cfg(feature_set="wide"))
    assert list(out.columns) == [*ob.FEATURE_SETS["wide"], "premium_share"]
    assert out.loc[3, "wing_missing"] == 1.0 and out["wing_missing"].sum() == 1.0
    pd.testing.assert_frame_equal(ob.build_feature_set(panel, _cfg()), ob.build_features(panel))
    panel.loc[0, "front_iv"] = 0.0
    with pytest.raises(ValueError, match="non-positive"):
        ob.build_feature_set(panel, _cfg(feature_set="wide"))


def test_state_roundtrip_with_groups(tmp_path: Path) -> None:
    frame, X, _ = _grouped_book(n_dates=40)
    cfg = _cfg(name_prior_scale=0.1, group_prior_scale=0.3)
    st = ob.run_online(frame, X, cfg, coef_names=["c", "a", "b"], quiet=True).state
    st.to_npz(tmp_path / "s.npz", {"k": 1})
    back, meta = ob.NIGState.from_npz(tmp_path / "s.npz")
    np.testing.assert_array_equal(back.m, st.m)
    assert back.groups == {str(k): v for k, v in st.groups.items()}
    assert back.names == {str(k): v for k, v in st.names.items()}
    assert back.group_scale == st.group_scale and meta == {"k": 1}


# ── the Yeo-Johnson loss-ratio target ────────────────────────────────────────


@pytest.mark.parametrize("k", [0.0, 0.25, 0.5, 1.0, 1.5])
def test_yj_inverse_and_jacobian(k: float) -> None:
    x = np.linspace(-3.0, 12.0, 301)
    np.testing.assert_allclose(ob.yj_inv(ob.yj(x, k), k), x, rtol=1e-10, atol=1e-10)
    h = 1e-6
    num = (ob.yj(x + h, k) - ob.yj(x - h, k)) / (2 * h)
    np.testing.assert_allclose(ob.yj_logderiv(x, k), np.log(num), atol=1e-5)
    if k == 1.0:
        np.testing.assert_allclose(ob.yj(x, k), x, atol=1e-12)


def _skewed_book(seed: int = 31) -> tuple[pd.DataFrame, np.ndarray]:
    """A seller's book: y = -U x, the loss ratio x normal on the Yeo-Johnson (k = 0) scale."""
    frame, X, _ = _book(n_dates=200, per_date=6, seed=seed)
    rng = np.random.default_rng(seed + 1)
    unit = rng.uniform(10.0, 30.0, len(frame))
    z = -0.1 + 0.3 * X[:, 1] + 0.45 * rng.standard_normal(len(frame))
    frame["y"] = -unit * ob.yj_inv(z, 0.0)
    frame["unit"] = unit
    return frame, X


def test_transformed_target_density_is_proper_on_the_original_scale() -> None:
    frame, X = _skewed_book()
    cfg = _cfg(target_transform="yj_loss", yj_power=0.0, obs_df=5.0)
    run = ob.run_online(frame.iloc[:400], X[:400], cfg, coef_names=["c", "a", "b"], quiet=True)
    i = int(np.flatnonzero(run.events["scored"].to_numpy())[0])
    ev = run.events.iloc[i]
    u = frame["unit"].iloc[i]
    ys = np.linspace(-80 * u, 40 * u, 600_001)
    x = -ys / u
    z = ob.yj(x, 0.0)
    one = np.ones_like(ys)
    mp = ob.mixture_predictive(
        z, ev["pred_loc"] * one, ev["pred_q"] * one, one * frame["v"].iloc[i],
        ev["pred_s2"] * one, ev["pred_df"] * one, cfg,
    )  # fmt: skip
    dens = np.exp(mp["log_score"] + ob.yj_logderiv(x, 0.0) - np.log(u))
    mass = float(np.sum((dens[1:] + dens[:-1]) / 2 * np.diff(ys)))
    assert mass == pytest.approx(1.0, abs=5e-3)
    below = ys <= 0
    p_le0 = float(np.sum((dens[1:] + dens[:-1])[below[1:]] / 2 * np.diff(ys)[below[1:]]))
    assert 1.0 - ev["p_pos"] == pytest.approx(p_le0, abs=5e-3)


def test_transformed_target_wins_on_a_skewed_book_and_recovers_the_driver() -> None:
    frame, X = _skewed_book()
    names = ["c", "a", "b"]
    plain = ob.run_online(frame, X, _cfg(obs_df=5.0), coef_names=names, quiet=True)
    tr = ob.run_online(
        frame, X, _cfg(target_transform="yj_loss", yj_power=0.0),
        coef_names=names, quiet=True,
    )  # fmt: skip
    sc = plain.events["scored"]
    assert tr.events.loc[sc, "log_score"].mean() > plain.events.loc[sc, "log_score"].mean() + 0.1
    # On the transformed scale the planted slope is 0.3 on feature a, 0 on b.
    assert tr.state.m[1] == pytest.approx(0.3, abs=0.03)
    assert abs(tr.state.m[2]) < 0.03
    pit = tr.events.loc[sc, "pit"].to_numpy()
    assert 0.03 < (pit < 0.05).mean() < 0.07 and 0.03 < (pit > 0.95).mean() < 0.07
    assert np.isfinite(tr.events.loc[sc, "pred_mean_y"]).all()
    # The median rule and P(y > 0) > 0.5 agree by construction.
    agree = (tr.events.loc[sc, "pred_median_y"] > 0) == tr.events.loc[sc, "decide"]
    assert agree.all()


def test_gauge_reads_the_seller_side_under_the_transform() -> None:
    frame, X = _skewed_book()
    cfg = _cfg(target_transform="yj_loss", yj_power=0.0)
    g = ob.run_online(frame, X, cfg, coef_names=["c", "a", "b"], quiet=True).gauge
    # The planted intercept -0.1 on the loss-ratio scale is a gain for the median trade.
    assert g["intercept"].iloc[-1] < 0
    assert g["p_mean_pos"].iloc[-1] > 0.95
