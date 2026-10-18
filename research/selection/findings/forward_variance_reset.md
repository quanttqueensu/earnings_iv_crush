# Forward-variance reset: terminated at the measurement stage

The forward-variance reset (FVR) asked whether the earnings jump cancels from the
difference of two total variances, `W_b - W_f`, leaving a forward variance whose
announcement-day change predicts its own subsequent reversal. It is terminated. Not on a
negative return result, and not on a negative diagnostic: the object it is built from
cannot be measured on any data this project can obtain without payment.

Nothing here is charged as a trial. No return was predicted and no position was scored.

---

## 1. Two measurement objections, both conceded

**Stage zero used `W(T) = T * sigma_ATM^2`.** That is a summary of one point on the smile,
not the integral the decomposition `W(T) = C(T) + J` assumes. Around an announcement the
risk-neutral density is strongly non-Gaussian, so Black-Scholes at-the-money implied
variance is not an additive total-variance measure and the additivity the whole
construction rests on fails at the measurement rather than in the economics.

**The within-name correlation did not establish what stage zero read into it.** Under the
literal decomposition the same `J` cancels algebraically from `W_b - W_f`, so a +0.42 to
+0.44 loading of the front-minus-back difference on the implied move is equally consistent
with true covariance between event magnitude and ordinary or post-event volatility. The
stage-zero reading is withdrawn.

The size of the first objection is now measured rather than argued. On expiries with a
strip wide enough to integrate, the model-free variance is a median **1.33 times** the
Black-Scholes ATM total variance. A one-third gap is not a refinement.

---

## 2. The cached chains cannot support the measure

Rebuilt on the standard model-free strip,

    W(T) = 2 * sum_i ( dK_i / K_i^2 ) * Q(K_i)  -  ( F/K_0 - 1 )^2

with `F` from put-call parity and `r = 0` by project convention. Script:
`scripts/research_fvr_modelfree.py`.

The cache holds a +/-20%-of-spot strike band, fetched for straddle marking. In units of
each expiry's own `sigma*sqrt(T)`, that is a median **0.56** on 2019-2024 and **0.84** on
2013-2018 for the back leg. Events clearing even a lenient 1.5 on both legs: **zero** and
**sixteen**. The measure recovers **0.721** of the BS back-month variance against **1.043**
on the front, which is the signature of truncation rather than of non-Gaussianity: the same
strike band covers far less of a 29-day distribution than of a 3-day one.

The truncation is not noise. It is a monotone function of the variable the diagnostic
regresses on:

| Implied-move quartile, 2019-2024 | Mean implied move | Back coverage | Recovery vs BS |
|---|---|---|---|
| Q1 smallest | 0.0307 | 0.83 | 0.888 |
| Q2 | 0.0430 | 0.65 | 0.777 |
| Q3 | 0.0557 | 0.52 | 0.689 |
| Q4 largest | 0.0845 | 0.36 | 0.541 |

corr(coverage, implied move) −0.669, corr(recovery, implied move) −0.619, corr(recovery,
coverage) +0.841. The model-free diagnostics duly flip against the BS versions: within-name
loading −0.4228 and −0.0155 against +0.4227 and +0.4420; corr(H, back variance change)
−0.318 and −0.450 against +0.678 and +0.871; the variance decomposition inverts to
front-dominant. A sign flip of that size between two blocks, in the direction a
size-dependent truncation would push it, is a measurement artefact. It overturns nothing.

---

## 3. The free feed is wider, and still not wide enough

The cache narrowness is a cache-building choice, not a feed limit: the DoltHub adapter
returns every listed strike when `spot` is None. Probe: `scripts/research_fvr_feed_probe.py`,
80 megacap events sampled from the 2019-2024 block inside feed coverage, 75 fetched, 224
expiries measured. Output: `outputs/research/fvr_feed_probe.csv`.

The feed serves roughly three and a half times the cached width, a median 18 to 19 reliable
strikes per expiry spanning about −0.31 to +0.20 in log-moneyness against the cached
+/-0.10. It lists a monthly ladder only: three expiries inside 120 days, no weeklies.

Coverage, per side, in units of that expiry's own `sigma*sqrt(T)`:

| DTE | n | Strikes | Put side | Call side | Both >= 2.5 | Both >= 3.0 |
|---|---|---|---|---|---|---|
| < 10 | 6 | 10.5 | 3.20 | 2.11 | 0.000 | 0.000 |
| 10-20 | 68 | 19 | 3.10 | 2.08 | 0.338 | 0.191 |
| 21-35 | 74 | 19 | 2.75 | 1.92 | 0.189 | 0.095 |
| 36-60 | 68 | 18 | 2.41 | 1.70 | 0.235 | 0.088 |
| > 60 | 8 | 20 | 2.40 | 1.68 | 0.000 | 0.000 |

The call side binds everywhere. Upside strikes are listed and quoted less far out in
standard-deviation units than downside strikes, so the constraint is one-sided and the
put-side figure alone would have been misleading.

**The strip has not converged where it can be checked.** On the 26 expiries clearing 3.0
units on both sides, the 2.5-unit estimate differs from the all-reliable-strikes estimate
by a median **9.55%**, and only **2 of 26** come inside 5%. The strikes beyond 3.0 units
carry a median **7.44%** of total variance. That is the fat tail the non-Gaussian objection
predicts, confirmed directly: around an announcement the strip needs to reach well past
three standard deviations before the integral settles.

The narrower comparison, 2.5 units against 3.0 units, gives a median 2.53% and passes 19 of
26. It should not be used. It compares two truncations of a strip that the wider comparison
shows is still accumulating mass, so it certifies convergence by declining to look where
the mass is.

**The event-level requirement fails outright.** The test needs two expiries, both alive
through +7 sessions, so that `H = F(+1) - F(-1)` and `Y = F(+7) - F(+2)` are formed from the
same economic object on both sides:

| Requirement | Events out of 75 |
|---|---|
| Two expiries, both sides >= 2.0 | 26 (0.347) |
| Two expiries, both sides >= 2.5 | 15 (0.200) |
| Two expiries, both sides >= 3.0 | 4 (0.053) |
| Two expiries, both sides >= 3.0, and converged | **0 (0.000)** |

Zero of 75 puts the 95% upper bound on the pass rate at about 4% by the rule of three. Even
at that bound a 50-event probe needs roughly 1,250 event fetches, and the binding failure is
convergence rather than count.

**The size dependence survives the wider feed.** corr(coverage, implied move) −0.399,
corr(recovery, implied move) −0.377. Across implied-move quartiles, coverage falls 1.92 to
1.67 and recovery falls 1.284 to 1.075. Milder than on the cached chains, where recovery
spanned 0.888 to 0.541, but still moving monotonically with the regressor. A run at a
relaxed 2.5-unit floor would therefore carry a bias in `W` that correlates at roughly −0.4
with the event size the cancellation diagnostic is regressing on, which is the same defect
in a smaller font.

One caveat cuts in the unfavourable direction: the sample is megacap, which carries the
widest and deepest listed chains of any US single-name universe. This is an upper bound on
what the free feed can do, not a typical case.

---

## 4. Verdict

Per the pre-registered rule, the free feed cannot supply sufficiently wide chains for a
usable sample, so the FVR stops here. It is not killed as an economic hypothesis and it is
not rescued: it is **untestable on obtainable data**. The distinction matters for anyone who
picks this record up. Nothing below has been shown about whether the earnings jump cancels
from the forward variance. The question was never reached.

Paying for wider chains was considered and rejected. The spend would buy the ability to
establish whether the signal can be *measured*, one stage before establishing whether it
exists, on a project whose headline result is already a settled negative.

**Carried forward instead:** delayed back-month and post-earnings implied-volatility
reversal, as a separately named modern executable replication. Not the FVR, not a novelty
claim, and it does not inherit any of the FVR's pre-registration.

---

## Artifacts

| File | Role |
|---|---|
| `scripts/research_fvr_stage0.py` | Stage-zero diagnostics on BS variance; reading withdrawn |
| `scripts/research_fvr_modelfree.py` | Model-free rebuild on cached chains |
| `scripts/research_fvr_feed_probe.py` | Free-feed width and strip-convergence probe |
| `outputs/research/fvr_modelfree.csv` | Per-event model-free measures, both blocks |
| `outputs/research/fvr_feed_probe.csv` | Per-expiry coverage and nested variance estimates |
