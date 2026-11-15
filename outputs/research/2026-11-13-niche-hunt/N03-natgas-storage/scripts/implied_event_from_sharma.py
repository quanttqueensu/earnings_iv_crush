"""implied_event_from_sharma.py: back out the storage-day event variance that a monthly NG option
implied over 1998-2013 from the mean implied-volatility changes in Sharma (2017, UGA MS thesis,
Table 4: mean 100*ln(IV_t/IV_{t-1}) of -0.905 on storage days and +0.481 on days with no
scheduled announcement; CRB nearest-the-money IV on nearby NYMEX NG options).

Model: total variance to expiry = n ordinary days plus m storage events each worth x extra days.
After a storage day, n -> n-1 and m -> m-1; after an ordinary day, n -> n-1. The storage-minus-
ordinary difference in log IV is 0.5*[ln(n-1+(m-1)x) - ln(n-1+mx)]. Solve for x given the
observed difference. Conjecture-grade: the ordinary-day change includes weekend and roll effects.

Usage: python -I scripts/implied_event_from_sharma.py
"""
from __future__ import annotations
import numpy as np
from scipy.optimize import brentq

obs = (-0.905 - 0.481) / 100.0
for n, m in ((10, 2), (15, 3), (21, 4)):
    g = lambda x: 0.5 * (np.log(n - 1 + (m - 1) * x) - np.log(n - 1 + m * x)) - obs
    x = brentq(g, 1e-6, 50.0)
    print(f"n={n} trading days to expiry, m={m} storage events left: implied event excess x = {x:.3f} ordinary days")
