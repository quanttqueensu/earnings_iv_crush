# Freeze: E3 spillover, trials 2742 and 2749

Frozen before any 2019-2024 peer-night outcome was computed. Exploratory regime (unhashed by
`protocol.freeze_prereg`; this note hashes itself and the scorer instead).

## Frozen rules

**2742, directional peer continuation.** For every (non-reporting peer, reaction session) pair
in `peer_nights.parquet` with reaction session in 2019-2024: s = sign of the mean abnormal
reaction (CRSP ret minus S&P 500 sprtrn) of the same-SIC3 reporters reacting that session, traded
only when its absolute value is at least 1%. Buy (s = +1) or short (s = -1) the peer at the close
of the reaction session, hedge with a beta-one S&P 500 leg, close at the next session's close.
Cost per side: the peer's CRSP closing half-spread plus 1 bp; hedge 0.3 bp plus 1 bp. Statistic:
mean net return per trade in basis points of peer notional, date-clustered 95% interval on the
reaction date. Pass: net CI excludes zero above and the gross mean sits above the 97.5th
percentile of the date-level sign-flip null. Otherwise fail.

**2749, peer variance ratio (option-arm gate).** Pooled ratio of the peer's squared raw return on
the reaction session to its mean squared raw return on control sessions 6 to 25 sessions either
side, excluding sessions on which the peer or any same-SIC3 universe name reacts and sessions from
2 before to 5 after any of the peer's own report windows. Date-clustered bootstrap, 5,000 draws.
Decision: upper bound below 3.4 closes buying peer variance without a pull; lower bound above
3.4 recommends the pull.

## Search behind the freeze

Twelve trial numbers (2742 to 2753) on discovery 2013-2018, 2748 unscored for want of data and
2753 withdrawn (own-report nights), plus a first pass on a peer set with an exclusion leak
(diagnosis.log entry 4). Nothing passed discovery; 2742's discovery t is about 1.2 gross
(+3.33 bp [-2.38, +8.90]) and net -4.51 bp [-10.20, +1.07]. These rules are frozen as declared,
not selected.

## Block

`block_is_clean` on `research/ledger/blocks.csv`: panel `peer_spillover_nights`, period 2019-24,
outcome families `peer_stock_return` and `peer_realised_variance`, feature family
`bellwether_reaction`: clean. The scorer logs its view to `block_views.csv` in this folder for the
team lead to append to the shared ledger.

## Hashes (SHA-256)

- held-out scorer `s06_heldout.py`: scorer_sha256: 4287d7833c6258b06059938050b58bb600111ca94021e29ae8a12f22f99c955a
- `spill.py`: 70667e23476e3a4a6ef5ce5228b8edf6cf5e76974eadc2f050c11b25a8f5b29d
- `lib.py`: 67650f002eaa31f5628deabc1e953562043eff6b13fa43bab75ce4c143da01a0
- `peer_nights.parquet`: 273863e3bc458bbb396e612fbf2344eade702f5d35d124998588f29874c99250
- `s01_peer_nights.py`: f323e741826f7fe0636785dd40dee06c92ad98299c22f0e119d54388aca4f21b
- this note, with this value read as PENDING: note_sha256: d7f46d913edf21a3ef22d12824758e3e3c053a9b824cc0aa30e38f9fe662030a
