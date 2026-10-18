"""
test_sync.py
The R2 cache sync against a local filesystem standing in for the bucket.

Pins: the manifest records exact bytes and hashes and skips excluded folders; the tracked pin
fixes the manifest's hash; pull fetches the manifest only if it matches the pin, then restores
exactly the manifest's bytes; pull refuses to start when the bucket lacks any file; a corrupted
download never replaces a local file; push refuses a stale manifest.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from pyarrow import fs as pafs

from earnings_iv_crush.data import sync


@pytest.fixture
def repo(tmp_path, monkeypatch):
    root = tmp_path / "repo"
    (root / "outputs" / "research").mkdir(parents=True)
    (root / "data" / "cache" / "x").mkdir(parents=True)
    (root / "data" / "cache" / "alpaca_legacy").mkdir(parents=True)
    (root / "outputs" / "research" / "events.parquet").write_bytes(b"events-v1")
    (root / "data" / "cache" / "x" / "chain.parquet").write_bytes(b"chain" * 1000)
    (root / "data" / "cache" / "alpaca_legacy" / "a.parquet").write_bytes(b"leaky")
    (root / "outputs" / "research" / "run.log").write_text("noise")
    monkeypatch.setattr(sync, "ROOT", root)
    monkeypatch.setattr(sync, "MANIFEST", root / "data" / "cache" / "MANIFEST.csv")
    monkeypatch.setattr(sync, "PIN", root / "data" / "MANIFEST.pin.json")
    bucket = tmp_path / "bucket"
    bucket.mkdir()
    local = pafs.SubTreeFileSystem(str(bucket), pafs.LocalFileSystem())
    monkeypatch.setattr(sync, "_remote", lambda: (local, "b/earnings_iv_crush"))
    return root, bucket


def _publish() -> list[sync.Entry]:
    entries = sync.build_manifest(progress=False)
    sync.write_manifest(entries)
    sync.write_pin(entries)
    return entries


def test_manifest_skips_logs_and_excluded_folders(repo) -> None:
    entries = _publish()
    assert [e.path for e in entries] == [
        "data/cache/x/chain.parquet",
        "outputs/research/events.parquet",
    ]
    assert sync.read_manifest() == entries
    pin = json.loads(sync.PIN.read_text(encoding="utf-8"))
    assert pin["files"] == 2 and pin["manifest_sha256"] == sync.sha256_of(sync.MANIFEST)
    assert set(pin["by_folder"]) == {"data/cache/x", "outputs/research"}


def test_push_then_fresh_pull_restores_exact_bytes(repo) -> None:
    root, _ = repo
    entries = _publish()
    sync.push(entries)
    original = (root / "data" / "cache" / "x" / "chain.parquet").read_bytes()
    # A teammate's clone: the pin is tracked, nothing else is present.
    sync.MANIFEST.unlink()
    (root / "data" / "cache" / "x" / "chain.parquet").unlink()
    (root / "outputs" / "research" / "events.parquet").write_bytes(b"tampered")
    sync.fetch_manifest()
    fetched = sync.read_manifest()
    assert fetched == entries
    sync.pull(fetched)
    assert (root / "data" / "cache" / "x" / "chain.parquet").read_bytes() == original
    assert sync.diff(fetched) == ([], [])


def test_manifest_that_does_not_match_the_pin_is_refused(repo) -> None:
    root, bucket = repo
    entries = _publish()
    sync.push(entries)
    sync.MANIFEST.unlink()
    remote = Path(bucket) / "b" / "earnings_iv_crush" / "MANIFEST.csv"
    remote.write_text("path,bytes,sha256\nforged,1,00\n", encoding="utf-8")
    with pytest.raises(ValueError, match="do not match"):
        sync.fetch_manifest()
    assert not sync.MANIFEST.exists()


def test_pull_refuses_an_incomplete_upload(repo) -> None:
    root, _ = repo
    entries = _publish()
    (root / "outputs" / "research" / "events.parquet").unlink()
    with pytest.raises(FileNotFoundError, match="not in the bucket"):
        sync.pull(entries)  # nothing was ever pushed


def test_corrupt_download_never_lands(repo) -> None:
    root, bucket = repo
    entries = _publish()
    sync.push(entries)
    remote = Path(bucket) / "b" / "earnings_iv_crush" / "outputs" / "research" / "events.parquet"
    remote.write_bytes(b"corrupted")
    (root / "outputs" / "research" / "events.parquet").unlink()
    with pytest.raises(ValueError, match="do not match"):
        sync.pull(entries)
    assert not (root / "outputs" / "research" / "events.parquet").exists()


def test_push_refuses_a_stale_manifest(repo) -> None:
    root, _ = repo
    entries = _publish()
    (root / "outputs" / "research" / "events.parquet").write_bytes(b"events-v2")
    with pytest.raises(ValueError, match="regenerate"):
        sync.push(entries)
