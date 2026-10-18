"""
sync.py
Share the research caches through the club's Cloudflare R2 bucket, verified by a pinned manifest.

The research inputs (OPRA quote marks, chain caches, WRDS-derived calendars, built event files)
are licensed or vendor-derived, so they never enter the repository. Two files describe them:

* ``data/cache/MANIFEST.csv`` (git-ignored, also stored in the bucket): one row per cached file
  with its path, size and SHA-256. It runs to tens of thousands of rows, too large to churn in git.
* ``data/MANIFEST.pin.json`` (tracked): the manifest's own SHA-256 and the file count and size
  per folder. A teammate's ``pull`` downloads the manifest, refuses it unless it matches the pin,
  then fetches exactly those files, re-hashing each before it lands.

Commands::

    python -m earnings_iv_crush.data.sync manifest   # hash the local caches; write manifest + pin
    python -m earnings_iv_crush.data.sync verify     # which manifest files are missing or differ
    python -m earnings_iv_crush.data.sync pull       # fetch missing or differing files from R2
    python -m earnings_iv_crush.data.sync push       # upload every file, then the manifest

Credentials come from ``.env``: ``IVCRUSH_R2_BUCKET`` and ``IVCRUSH_R2_PREFIX``; the endpoint and
keys from the ``IVCRUSH_R2_*`` names, falling back to the WRDS mirror's ``R2_*`` names. Pushing
needs a key with write access. Folders of closed or excluded work are not shared (``EXCLUDE``).

Usage
-----
    python -m earnings_iv_crush.data.sync pull --only outputs/research
    python -m earnings_iv_crush.data.sync verify
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
from collections import Counter
from collections.abc import Callable, Iterable
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from functools import partial
from pathlib import Path
from typing import Any

from . import config

ROOT = Path(__file__).resolve().parents[2]
MANIFEST = ROOT / "data" / "cache" / "MANIFEST.csv"
PIN = ROOT / "data" / "MANIFEST.pin.json"
REMOTE_MANIFEST = "MANIFEST.csv"
# Research inputs and built artefacts. Live paper-book state (outputs/live) is each
# operator's own record and is never shared.
ROOTS = ("outputs/research", "data/cache", "data/processed")
# Not shared, by name, with the reason. Closed lines keep their code; their raw caches are
# not needed to read their findings, and the Alpaca caches must not feed selection at all.
EXCLUDE: dict[str, str] = {
    "data/cache/MANIFEST.csv": "the manifest itself",
    "data/cache/alpaca_legacy/": "legacy Alpaca pulls; Alpaca features leak and are never used",
    "data/processed/alpaca_chain_": "per-event Alpaca chains; same reason",
    "data/processed/lse": "London Strategic Edge, evaluated and not adopted",
    "data/processed/nse_fo/": "India, a closed geography",
    "data/processed/b3_cotahist/": "Brazil, a closed geography",
}
SKIP_SUFFIXES = (".log", ".err", ".bak", ".pyc", ".tmp", ".part")
COLUMNS = ["path", "bytes", "sha256"]
CHUNK = 1 << 20
WORKERS = 32  # R2 serves many small objects well in parallel; one at a time takes hours


@dataclass(frozen=True)
class Entry:
    path: str
    bytes: int
    sha256: str


# ── hashing and the manifest ─────────────────────────────────────────────────


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(CHUNK), b""):
            h.update(block)
    return h.hexdigest()


def _shared(rel: str) -> bool:
    return not rel.endswith(SKIP_SUFFIXES) and not any(rel.startswith(x) for x in EXCLUDE)


def local_files(roots: Iterable[str] = ROOTS) -> list[Path]:
    """Every shareable file under the cache roots, sorted."""
    out: list[Path] = []
    for root in roots:
        base = ROOT / root
        if base.exists():
            out.extend(
                p
                for p in base.rglob("*")
                if p.is_file()
                and "__pycache__" not in p.parts
                and _shared(p.relative_to(ROOT).as_posix())
            )
    return sorted(out)


def build_manifest(roots: Iterable[str] = ROOTS, *, progress: bool = True) -> list[Entry]:
    files = local_files(roots)

    def one(p: Path) -> Entry:
        return Entry(p.relative_to(ROOT).as_posix(), p.stat().st_size, sha256_of(p))

    entries: list[Entry] = []
    with ThreadPoolExecutor(max_workers=8) as pool:
        for i, entry in enumerate(pool.map(one, files), 1):
            entries.append(entry)
            if progress and (i % 5000 == 0 or i == len(files)):
                print(f"  hashed {i}/{len(files)}", flush=True)
    return entries


def write_manifest(entries: list[Entry], path: Path | None = None) -> None:
    # Paths resolve at call time, so a caller that relocates them (the tests) is honoured.
    path = MANIFEST if path is None else path
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh, lineterminator="\n")
        w.writerow(COLUMNS)
        for e in entries:
            w.writerow([e.path, e.bytes, e.sha256])


def write_pin(entries: list[Entry], manifest: Path | None = None, pin: Path | None = None) -> dict:
    manifest = MANIFEST if manifest is None else manifest
    pin = PIN if pin is None else pin
    files, size = Counter[str](), Counter[str]()
    for e in entries:
        parts = e.path.split("/")
        # data/<cache|processed>/<folder> or outputs/research; loose files group by their parent
        depth = 3 if parts[0] == "data" and len(parts) > 3 else 2
        top = "/".join(parts[:depth])
        files[top] += 1
        size[top] += e.bytes
    body = {
        "manifest_sha256": sha256_of(manifest),
        "files": len(entries),
        "bytes": sum(e.bytes for e in entries),
        "by_folder": {k: {"files": files[k], "bytes": size[k]} for k in sorted(files)},
    }
    pin.write_text(json.dumps(body, indent=2) + "\n", encoding="utf-8")
    return body


def read_manifest(path: Path | None = None) -> list[Entry]:
    path = MANIFEST if path is None else path
    if not path.exists():
        raise FileNotFoundError(
            f"{path} not found; `python -m earnings_iv_crush.data.sync pull` fetches it."
        )
    with path.open(newline="", encoding="utf-8") as fh:
        return [Entry(r["path"], int(r["bytes"]), r["sha256"]) for r in csv.DictReader(fh)]


def diff(entries: list[Entry]) -> tuple[list[Entry], list[Entry]]:
    """(missing locally, present but different) against the manifest."""
    missing, changed = [], []
    for e in entries:
        p = ROOT / e.path
        if not p.exists():
            missing.append(e)
        elif p.stat().st_size != e.bytes or sha256_of(p) != e.sha256:
            changed.append(e)
    return missing, changed


# ── the bucket ───────────────────────────────────────────────────────────────


def _env(name: str, fallback: str | None) -> str | None:
    return os.environ.get(name) or fallback


def _remote() -> tuple[Any, str]:
    """(filesystem, bucket/prefix) for the team-data bucket, from ``.env``."""
    from pyarrow.fs import S3FileSystem

    endpoint = _env("IVCRUSH_R2_ENDPOINT_URL", config.R2_ENDPOINT_URL)
    key = _env("IVCRUSH_R2_ACCESS_KEY_ID", config.R2_ACCESS_KEY_ID)
    secret = _env("IVCRUSH_R2_SECRET_ACCESS_KEY", config.R2_SECRET_ACCESS_KEY)
    bucket = os.environ.get("IVCRUSH_R2_BUCKET")
    prefix = os.environ.get("IVCRUSH_R2_PREFIX", "earnings_iv_crush").strip("/")
    if not (endpoint and key and secret and bucket):
        raise RuntimeError(
            "Team-data bucket not configured. Set IVCRUSH_R2_BUCKET (and, if they differ from "
            "the WRDS mirror's, IVCRUSH_R2_ENDPOINT_URL / _ACCESS_KEY_ID / _SECRET_ACCESS_KEY) "
            "in .env. Ask the team lead for the values."
        )
    fs = S3FileSystem(
        access_key=key,
        secret_key=secret,
        endpoint_override=endpoint.removeprefix("https://"),
        scheme="https",
        region="auto",
    )
    return fs, f"{bucket}/{prefix}"


def _download(fs: Any, key: str, target: Path, sha: str) -> None:
    """Fetch one object to a temporary name, verify its hash, then move it into place."""
    target.parent.mkdir(parents=True, exist_ok=True)
    part = target.with_name(target.name + ".part")
    with fs.open_input_stream(key) as src, part.open("wb") as dst:
        while block := src.read(CHUNK):
            dst.write(block)
    if sha256_of(part) != sha:
        part.unlink()
        raise ValueError(f"{target}: downloaded bytes do not match the manifest hash")
    part.replace(target)


def _upload(fs: Any, src: Path, key: str) -> None:
    # Object stores have no directories, but a filesystem stand-in does.
    fs.create_dir(key.rsplit("/", 1)[0], recursive=True)
    with src.open("rb") as fh, fs.open_output_stream(key) as dst:
        while block := fh.read(CHUNK):
            dst.write(block)


def _parallel(jobs: list[Callable[[], None]], label: str) -> None:
    done = 0
    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        for fut in as_completed([pool.submit(j) for j in jobs]):
            fut.result()  # re-raise the first failure
            done += 1
            if done % 2000 == 0 or done == len(jobs):
                print(f"  {label} {done}/{len(jobs)}", flush=True)


def fetch_manifest() -> None:
    """Download the bucket's manifest and accept it only if it matches the tracked pin."""
    if not PIN.exists():
        raise FileNotFoundError(f"{PIN} not found; the lead publishes it with `sync push`.")
    pinned = json.loads(PIN.read_text(encoding="utf-8"))["manifest_sha256"]
    if MANIFEST.exists() and sha256_of(MANIFEST) == pinned:
        return
    fs, base = _remote()
    _download(fs, f"{base}/{REMOTE_MANIFEST}", MANIFEST, pinned)


def pull(entries: list[Entry]) -> None:
    """Download every missing or differing file, re-hashing each before it lands."""
    from pyarrow.fs import FileType

    missing, changed = diff(entries)
    todo = missing + changed
    if not todo:
        print("Local caches match the manifest; nothing to pull.")
        return
    fs, base = _remote()
    infos = fs.get_file_info([f"{base}/{e.path}" for e in todo])
    absent = [e.path for e, i in zip(todo, infos, strict=True) if i.type != FileType.File]
    if absent:
        raise FileNotFoundError(
            f"{len(absent)} manifest file(s) are not in the bucket (first: {absent[:5]}); "
            "the upload is incomplete. Nothing was downloaded."
        )
    _parallel(
        [partial(_download, fs, f"{base}/{e.path}", ROOT / e.path, e.sha256) for e in todo],
        "pulled",
    )


def push(entries: list[Entry]) -> None:
    """Upload every manifest file, then the manifest, so the bucket never lists absent files."""
    missing, changed = diff(entries)
    if missing or changed:
        bad = [e.path for e in (missing + changed)[:5]]
        raise ValueError(
            f"{len(missing) + len(changed)} local file(s) are missing or differ from the "
            f"manifest; regenerate it first (first: {bad})."
        )
    fs, base = _remote()
    _parallel([partial(_upload, fs, ROOT / e.path, f"{base}/{e.path}") for e in entries], "pushed")
    _upload(fs, MANIFEST, f"{base}/{REMOTE_MANIFEST}")


# ── cli ──────────────────────────────────────────────────────────────────────


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description="Share research caches through R2, hash-verified.")
    ap.add_argument("command", choices=("manifest", "verify", "pull", "push"))
    ap.add_argument("--only", default=None, help="restrict to paths under this prefix")
    args = ap.parse_args(argv)

    if args.command == "manifest":
        entries = build_manifest()
        write_manifest(entries)
        body = write_pin(entries)
        print(
            f"Wrote {MANIFEST.relative_to(ROOT)} and {PIN.relative_to(ROOT)}: "
            f"{body['files']} files, {body['bytes'] / 1e9:.2f} GB."
        )
        return
    if args.command == "pull":
        fetch_manifest()
    entries = read_manifest()
    if args.only:
        entries = [e for e in entries if e.path.startswith(args.only)]
    if args.command == "verify":
        missing, changed = diff(entries)
        print(f"{len(entries)} manifest files: {len(missing)} missing, {len(changed)} differ.")
        for e in (missing + changed)[:20]:
            print(f"  {e.path}")
        if missing or changed:
            raise SystemExit(1)
    elif args.command == "pull":
        pull(entries)
    else:
        push(entries)


if __name__ == "__main__":
    main()
