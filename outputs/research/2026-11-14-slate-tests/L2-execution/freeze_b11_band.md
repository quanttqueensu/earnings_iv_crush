# Freeze note: B11 delta band with stock commission (trials 2,907 to 2,916)

Written after the 2013-18 discovery read (diagnosis.log entries [23] and [24]) and before any
2019-24 band outcome was computed. The scorer b11_band.py, its helpers l2fees.py and l2lib.py,
and the discovery output that names the champion are frozen as hashed below. The scorer runs a
non-discovery block only when this note verifies, and then values only band 0 and the champion.

Champion by the declared rule (highest 1-contract paired mean on 2013-18): band 0.30 shares per
straddle-share, discovery +0.123 [+0.042, +0.204] % of m0, N = 2,640, variance ratio 1.033
[1.021, 1.045]. It is the edge of the grid.

Rule, unchanged: hedge set to the Black-Scholes target at the reaction close; at each later
hedging close re-set to the target only when it differs from the position held (after any
assignment delivery) by more than the band; netted expiry residual always trades. Every nonzero
stock order pays IBKR Tiered with the 1% cap (recalled), in both arms.

Test: 2019-24, read once. Primary: paired (H_band - comm) - (H_0 - comm) at 1 contract, per
trade, % of m0, net at the touch, date-clustered 95%. Pass: interval above zero. Secondary: the
same at 5 contracts; the variance ratio; the decomposition. The hedged_hold outcome on 2019-24
was viewed by earlier studies (block_is_clean is True only for this feature family), so the read
is labelled exploratory held-out whatever its result. Command:
python outputs/research/2026-11-14-slate-tests/L2-execution/b11_band.py --block 2019-24

Frozen files (sha256):
- b11_band.py: dfb2cca63e4077ff15efeea31be23faf125c57b40f1d7ab90d1e76e8171cf5ed
- l2fees.py: c2426cff1c3b3aa9bb66104fd719ca39989b406901c09f75f828cfdb9f1d1d3e
- l2lib.py: ed65c9025e91eb16c2e11e56bf5fe9e924f8f7fcf6e27bc14abeed68d7160a63
- b11_2013-18.json: 454c4470d27921065e3f6ba90a294bec180552ff0cbf97061865f53aa65f4cc3

Self sha256 (sha256 of every byte above this line, LF endings): a36c7dc4f1187331ea9f00f1f112f6ab272e84b4e86320b66929392b97ac4fa7
