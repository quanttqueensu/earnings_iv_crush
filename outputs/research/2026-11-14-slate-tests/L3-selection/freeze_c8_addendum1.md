# Trial 2,953 freeze note, addendum 1: the stock-volume input

Written 2026-11-15 after the held-out read, at a reviewer's request. It does not edit
freeze_c8.md, whose own hash still verifies, and it changes no rule, threshold or result.

freeze_c8.md hashed the scorer, lib.py and the panel c8_megacap_corrected.parquet, but not the
second input the scorer reads, c8_stock_volume.parquet (CRSP D-1 share volume, written 02:15 EST,
before the discovery read at 02:17 EST and the held-out read at 02:19 EST). The file hashed below
is the one both reads used: re-running c8_stock_volume.py at 03:16 EST reproduced it byte for
byte, so its hash then equals its hash at the time of the reads. c8_megacap_corrected.parquet was
reproduced byte for byte by the same re-run and still matches the hash in freeze_c8.md.

c8_stock_volume.parquet sha256 079f280486363f59ed373863f2a20817110511d1fa59c485437325a235758014
c8_megacap_corrected.parquet sha256 dc7ec4a367bc7f7de6ed89717f51cf369077ea5c3be05d705e2ad796d231c489
Note sha256 (of every byte above this line): 72bdc8f06f9f78855c29f85f361c533fb412d4c6e592a852e4b2b2c12e91004a
