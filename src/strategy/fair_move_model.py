"""Fair-move regression: the model-implied event move.

An empirical proxy for the Dubinsky-Johannes (2006) event-variance estimator.
Regresses the realised post-earnings move on five pre-event features so the
filter can compare the market's implied move against a fair benchmark.

OLS via statsmodels. The model fits on whichever of FEATURES are actually
present and populated, so it works today on the two features the pipeline can
compute (trailing_rv, skew_25d) and automatically widens as eps_dispersion,
prior_surprise and oi_growth come online. The walk-forward helper sets up the
31 July milestone: it never fits on data later than the event it predicts.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import statsmodels.api as sm

FEATURES = [
    "trailing_rv",      # trailing realised volatility
    "skew_25d",         # 25-delta IV skew (jump-risk proxy)
    "eps_dispersion",   # analyst EPS dispersion
    "prior_surprise",   # prior earnings surprise magnitude
    "oi_growth",        # pre-event open-interest growth
]


class FairMoveModel:
    """Fit-and-predict wrapper around the fair-move regression."""

    def __init__(self, features=None):
        self.features = list(features) if features is not None else list(FEATURES)
        self.result = None
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
        design = sm.add_constant(X[mask], has_constant="add")
        self.result = sm.OLS(y[mask], design).fit()
        self.used_features = cols
        return self

    def predict(self, events: pd.DataFrame) -> pd.Series:
        """Return the fair (model-implied) event move for each event.

        Clipped at zero, since an absolute move cannot be negative.
        """
        if self.result is None:
            raise RuntimeError("call fit() before predict()")
        X = events[self.used_features].astype(float).reset_index(drop=True)
        design = sm.add_constant(X, has_constant="add")
        pred = np.asarray(self.result.predict(design), dtype=float)
        return pd.Series(np.clip(pred, 0.0, None), index=events.index)

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
                model = FairMoveModel(self.features).fit(train, y.iloc[:i])
            except ValueError:
                continue
            preds.iloc[i] = model.predict(events.iloc[[i]]).iloc[0]
        return preds
