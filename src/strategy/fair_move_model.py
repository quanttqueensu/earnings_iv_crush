"""fair_move_model.py
Fair-move regression: the model-implied event move.

An empirical proxy for the Dubinsky-Johannes (2006) event-variance estimator.
Regresses the realised post-earnings move on up to five pre-event features so
the filter can compare the market's implied move against a fair benchmark.

The model fits on whichever of ``FEATURES`` are actually present and populated,
so it works today on the two features the pipeline can compute (``trailing_rv``,
``skew_25d``) and widens automatically as ``eps_dispersion``, ``prior_surprise``
and ``oi_growth`` come online. An ordinary least-squares fit (statsmodels)
exposes coefficient t-statistics; a ridge variant (scikit-learn) is available
for when the full, partly collinear feature set arrives. The walk-forward helper
never fits on data later than the event it predicts, and ``evaluate_walk_forward``
reports the out-of-sample skill that the 31 July validation milestone needs.

This module implements:

* ``FairMoveModel``           — fit / predict, OLS or ridge.
* ``FairMoveModel.diagnostics`` — R-squared, adjusted R-squared, t-statistics.
* ``FairMoveModel.evaluate_walk_forward`` — out-of-sample R-squared, calibration.

References
----------
Dubinsky, A., & Johannes, M. (2006). Earnings announcements and equity options.
*Working paper, Columbia Business School*.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import statsmodels.api as sm

FEATURES = [
    "trailing_rv",            # trailing realised volatility
    "skew_25d",               # 25-delta IV skew (jump-risk proxy)
    "eps_dispersion",         # analyst EPS dispersion
    "prior_surprise",         # prior earnings surprise magnitude
    "oi_growth",              # pre-event open-interest growth
    "vol_premium",            # front IV - trailing RV (Goyal & Saretto 2009)
    "variance_risk_premium",  # front IV^2 - trailing RV^2 (Bollerslev-Tauchen-Zhou 2009)
    "bkm_skew",               # model-free risk-neutral skew (Bakshi-Kapadia-Madan 2003)
    "bkm_kurt",               # model-free risk-neutral kurtosis (BKM 2003)
]


class FairMoveModel:
    """
    Fit-and-predict wrapper around the fair-move regression.

    Parameters
    ----------
    features : sequence of str, optional
        Candidate feature columns. Defaults to the full ``FEATURES`` list; the
        fit uses only those present and not entirely missing.
    method : str, optional
        ``"ols"`` (default) for an ordinary least-squares fit with t-statistics,
        or ``"ridge"`` for an L2-regularised fit robust to collinearity.
    alpha : float, optional
        Ridge regularisation strength. Ignored for OLS. Defaults to ``1.0``.
    """

    def __init__(self, features=None, method: str = "ols", alpha: float = 1.0):
        self.features = list(features) if features is not None else list(FEATURES)
        self.method = method.lower()
        self.alpha = float(alpha)
        self.result = None          # statsmodels result (OLS only)
        self._sk = None             # fitted sklearn estimator (ridge only)
        self.used_features: list[str] = []

    def _usable_features(self, events: pd.DataFrame) -> list[str]:
        """Features present in the frame and not entirely missing."""
        return [c for c in self.features
                if c in events.columns and events[c].notna().any()]

    def fit(self, events: pd.DataFrame, realised_move) -> "FairMoveModel":
        """Fit on historical events; target is the realised absolute event move."""
        cols = self._usable_features(events)
        if not cols:
            raise ValueError("no usable features to fit the fair-move model")
        X = events[cols].astype(float).reset_index(drop=True)
        y = pd.Series(np.asarray(realised_move, dtype=float)).reset_index(drop=True)

        mask = X.notna().all(axis=1) & y.notna()
        if mask.sum() <= len(cols):
            raise ValueError("not enough complete rows to fit the fair-move model")

        Xm, ym = X[mask], y[mask]
        if self.method == "ridge":
            from sklearn.linear_model import Ridge
            self._sk = Ridge(alpha=self.alpha).fit(Xm, ym)
        else:
            design = sm.add_constant(Xm, has_constant="add")
            self.result = sm.OLS(ym, design).fit()
        self.used_features = cols
        return self

    def predict(self, events: pd.DataFrame) -> pd.Series:
        """Return the fair (model-implied) event move for each event.

        Clipped at zero, since an absolute move cannot be negative.
        """
        if self.result is None and self._sk is None:
            raise RuntimeError("call fit() before predict()")
        X = events[self.used_features].astype(float).reset_index(drop=True)
        if self.method == "ridge":
            pred = self._sk.predict(X)
        else:
            pred = np.asarray(self.result.predict(sm.add_constant(X, has_constant="add")),
                              dtype=float)
        return pd.Series(np.clip(np.asarray(pred, dtype=float), 0.0, None), index=events.index)

    def diagnostics(self) -> dict:
        """In-sample fit diagnostics.

        Returns
        -------
        dict
            ``method``, ``n_obs``, ``r_squared``, ``adj_r_squared``, ``params``
            (coefficient dict) and ``tstats`` (coefficient t-statistics, ``None``
            for ridge which has no closed-form standard errors here).
        """
        if self.method == "ols":
            if self.result is None:
                raise RuntimeError("call fit() before diagnostics()")
            return {
                "method": "ols",
                "n_obs": int(self.result.nobs),
                "r_squared": float(self.result.rsquared),
                "adj_r_squared": float(self.result.rsquared_adj),
                "params": {k: float(v) for k, v in self.result.params.items()},
                "tstats": {k: float(v) for k, v in self.result.tvalues.items()},
            }
        if self._sk is None:
            raise RuntimeError("call fit() before diagnostics()")
        params = {"const": float(self._sk.intercept_)}
        params.update({c: float(b) for c, b in zip(self.used_features, self._sk.coef_)})
        return {
            "method": "ridge",
            "n_obs": None,
            "r_squared": None,
            "adj_r_squared": None,
            "params": params,
            "tstats": None,
        }

    def fit_predict_walk_forward(self, events: pd.DataFrame, realised_move,
                                 min_train: int = 20) -> pd.Series:
        """Expanding-window out-of-sample fair move (no look-ahead).

        For each event i >= min_train, fit on events [0, i) and predict event i.
        Assumes `events` is already sorted by announcement date.
        """
        y = pd.Series(np.asarray(realised_move, dtype=float), index=events.index)
        preds = pd.Series(np.nan, index=events.index, dtype=float)
        for i in range(len(events)):
            if i < min_train:
                continue
            train = events.iloc[:i]
            try:
                model = FairMoveModel(self.features, self.method, self.alpha).fit(
                    train, y.iloc[:i]
                )
            except ValueError:
                continue
            preds.iloc[i] = model.predict(events.iloc[[i]]).iloc[0]
        return preds

    def evaluate_walk_forward(self, events: pd.DataFrame, realised_move,
                              min_train: int = 20) -> dict:
        """Out-of-sample skill of the walk-forward fair move.

        Fits the expanding-window predictions and scores them against the
        realised move: an honest read of whether the fair-move model generalises,
        free of the in-sample R-squared's optimism.

        Returns
        -------
        dict
            ``n_oos`` (scored events), ``oos_r2`` (out-of-sample R-squared),
            ``corr`` (prediction-vs-realised correlation), ``mae`` (mean absolute
            error) and ``calibration_slope`` / ``calibration_intercept`` from
            regressing realised on predicted (slope ``1`` is perfect calibration).
            All-``nan`` when fewer than three events are scored.
        """
        y = pd.Series(np.asarray(realised_move, dtype=float), index=events.index)
        preds = self.fit_predict_walk_forward(events, realised_move, min_train)
        mask = preds.notna() & y.notna()
        y_true, y_pred = y[mask].to_numpy(), preds[mask].to_numpy()

        nan = float("nan")
        if y_true.size < 3:
            return {"n_oos": int(y_true.size), "oos_r2": nan, "corr": nan,
                    "mae": nan, "calibration_slope": nan, "calibration_intercept": nan}

        ss_res = float(np.sum((y_true - y_pred) ** 2))
        ss_tot = float(np.sum((y_true - y_true.mean()) ** 2))
        oos_r2 = 1.0 - ss_res / ss_tot if ss_tot > 0 else nan
        corr = float(np.corrcoef(y_true, y_pred)[0, 1]) if y_pred.std() > 0 else nan
        mae = float(np.mean(np.abs(y_true - y_pred)))
        if y_pred.std() > 0:
            slope, intercept = np.polyfit(y_pred, y_true, 1)
        else:
            slope, intercept = nan, nan
        return {
            "n_oos": int(y_true.size),
            "oos_r2": float(oos_r2),
            "corr": corr,
            "mae": mae,
            "calibration_slope": float(slope),
            "calibration_intercept": float(intercept),
        }
