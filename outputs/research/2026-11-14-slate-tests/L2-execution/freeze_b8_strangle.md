# Freeze note: B8 strangle width from the 1,623 move forecast (trial 2,906)

Written after the 2016-18 discovery read (diagnosis.log entry [18]) and before any 2019-24 read.
The scorer b8_strangle.py and its helper l2lib.py are frozen as hashed below, with the two caches
it reads: the 1,623 walk-forward forecasts (built by the closed study's own code, unchanged) and
the strangles built for every event of 2016-24 before any scoring. b8_strangle.py was formatted
with black and ruff after the discovery run; no statement's logic changed.

Discovery failed the declared pass rule (+0.018 [-0.114, +0.151], N = 898), so the 2019-24 read is
exploratory and cannot make B8 a finding.

block_is_clean (research/ledger/blocks.csv), period 2019-24, outcome hedged_hold, feature family
execution_strangle_width_forecast: True for base_corrected; the hedged_hold outcome and the 1,623
move outcome on 2019-24 have been viewed before.

Reading: the primary (forecast-width strangle minus IM/2 strangle), each strangle against the
straddle on H_net, and the component split, with `b8_strangle.py --block 2019-24`.

Caches: _cache/b8_forecast.parquet sha256 a9281b792a41356a6b81c9c08f28e0e9a55f3412c40eb713c9fcf9720778b0b3; _cache/b8_built.parquet sha256 89b027aa062d25e2777aa3c79f76a8fd36dc7e3be03fd42d972c2d8f9b094110

Frozen files (sha256):
- b8_strangle.py: 607459e33707c78ddf6e7bcfac2fadf5aef01da2031e39d2cf2de45233455b49
- l2lib.py: ed65c9025e91eb16c2e11e56bf5fe9e924f8f7fcf6e27bc14abeed68d7160a63

Self sha256 (sha256 of every byte above this line, LF endings): 08c991c889484aa211f4baff4c09a5512d671c211bdeb79db0f5e4921e1867bf
