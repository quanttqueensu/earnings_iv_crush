"""
orient.py
Where the project stands right now, measured rather than quoted.

Documents carry rules and dated observations; this command carries state. Each section reads the
thing it reports (git, the cache manifest, the paper book's stores and switches, the gateway
port, the pre-registration records) and prints ``UNMEASURED`` with the reason when it cannot,
never a remembered number. Start every working session with it.

Usage
-----
    python -m earnings_iv_crush.ops.orient
    python -m earnings_iv_crush.ops.orient --hash    # also verify cache files against their hashes
"""

from __future__ import annotations

import argparse
import json
import socket
import subprocess
from collections.abc import Callable
from pathlib import Path

import pandas as pd

from ..config import LIVE

ROOT = Path(__file__).resolve().parents[2]
PAPER_PORTS = (7497, 4002)


def _git(*args: str) -> str:
    out = subprocess.run(
        ["git", *args], cwd=ROOT, capture_output=True, text=True, timeout=10, check=True
    )
    return out.stdout.strip()


def section_repo() -> list[str]:
    branch = _git("rev-parse", "--abbrev-ref", "HEAD")
    head = _git("log", "-1", "--format=%h %ad %s", "--date=short")
    dirty = len([line for line in _git("status", "--porcelain").splitlines() if line.strip()])
    tags = _git("tag", "--list", "paper-*", "--sort=-creatordate").splitlines()
    return [
        f"branch {branch} at {head}",
        f"{dirty} uncommitted path(s)",
        f"paper book tag in force: {tags[0] if tags else 'none'}",
    ]


def section_data(verify_hashes: bool) -> list[str]:
    from ..data import sync

    if not sync.MANIFEST.exists():
        pin = json.loads(sync.PIN.read_text(encoding="utf-8"))
        return [
            f"pinned manifest: {pin['files']} files, {pin['bytes'] / 1e9:.2f} GB "
            "(not yet fetched)",
            "  fetch with: python -m earnings_iv_crush.data.sync pull",
        ]
    entries = sync.read_manifest()
    if verify_hashes:
        missing, changed = sync.diff(entries)
    else:
        missing = [e for e in entries if not (ROOT / e.path).exists()]
        changed = [
            e
            for e in entries
            if (ROOT / e.path).exists() and (ROOT / e.path).stat().st_size != e.bytes
        ]
    gb = sum(e.bytes for e in entries) / 1e9
    lines = [f"manifest: {len(entries)} files, {gb:.2f} GB"]
    lines.append(
        f"local: {len(entries) - len(missing) - len(changed)} present, {len(missing)} missing, "
        f"{len(changed)} differ ({'hash' if verify_hashes else 'size'} check)"
    )
    if missing:
        lines.append("  fetch with: python -m earnings_iv_crush.data.sync pull")
    return lines


def section_switches() -> list[str]:
    marks = {
        "TRANSMIT_OK": ROOT / "_private" / "TRANSMIT_OK",
        "STOP": ROOT / LIVE.kill_switch_file,
        "HALT": ROOT / LIVE.halt_file,
    }
    lines = [f"{name}: {'PRESENT' if p.exists() else 'absent'}" for name, p in marks.items()]
    up = []
    for port in PAPER_PORTS:
        try:
            with socket.create_connection((LIVE.ib_host, port), timeout=0.5):
                up.append(port)
        except OSError:
            pass
    lines.append(
        f"gateway: listening on {up}" if up else f"gateway: nothing on paper ports {PAPER_PORTS}"
    )
    lines.append(
        f"config: universe {LIVE.universe_path}, cap {LIVE.max_names_per_day} names / "
        f"{LIVE.max_contracts_per_leg} contracts, market data type {LIVE.ib_market_data_type}, "
        f"session-aware {LIVE.session_aware_timing}"
    )
    return lines


def section_book() -> list[str]:
    from ..live import paper_book
    from ..live.order_events import completeness_share, load_order_events

    lines = []
    for label, base in (("live", Path(".")), ("dry", Path(LIVE.dry_dir))):
        open_path = ROOT / (
            base / Path(LIVE.open_positions_path).name
            if label == "dry"
            else LIVE.open_positions_path
        )
        book = paper_book.load_open_positions(open_path)
        lines.append(f"{label}: {len(book)} open position(s)")
    beat = paper_book.load_heartbeat(ROOT / LIVE.heartbeat_path)
    if beat.empty:
        lines.append("last transmitting pass: none recorded")
    else:
        row = beat.iloc[-1]
        lines.append(
            f"last transmitting pass {pd.Timestamp(row['asof']).date()}: "
            f"{int(row['n_candidates'])} candidates, {int(row['n_entered'])} entered"
        )
    events = load_order_events(ROOT / LIVE.order_events_path)
    share = completeness_share(events)
    lines.append(
        "order lifecycles: none yet"
        if share != share
        else f"order lifecycles complete: {share:.1%} of {events['order_id'].nunique()}"
    )
    return lines


def section_research() -> list[str]:
    records = sorted((ROOT / "outputs" / "research").glob("prereg_*.json"))
    counts = []
    for rec in records:
        body = json.loads(rec.read_text(encoding="utf-8"))
        for key in ("trial_count_after", "dsr_trial_count"):
            if isinstance(body.get(key), int):
                counts.append((body[key], rec.name, body.get("declared_utc", "")))
    preregs = list((ROOT / "research").glob("*/preregs/*.md"))
    lines = [f"{len(preregs)} pre-registration texts, {len(records)} hash records"]
    if counts:
        n, name, when = max(counts)
        lines.append(
            f"largest trial count in a hash record: {n} ({name}, {when}); later declarations "
            "are listed in docs/RESEARCH_STATE.md"
        )
    frozen_input = ROOT / "outputs" / "research" / "events_megacap_databento.parquet"
    lines.append(
        "frozen book reproducible: run python scripts/validate_screen.py"
        if frozen_input.exists()
        else "frozen book: inputs absent (sync pull), cannot reproduce here"
    )
    return lines


def _run(title: str, fn: Callable[[], list[str]]) -> None:
    print(f"\n{title}")
    try:
        for line in fn():
            print(f"  {line}")
    except Exception as exc:  # noqa: BLE001 - one unmeasurable section must not hide the rest
        print(f"  UNMEASURED: {type(exc).__name__}: {exc}")


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description="Measured project state.")
    ap.add_argument("--hash", action="store_true", help="verify cache files by SHA-256")
    args = ap.parse_args(argv)
    print(f"orient: {ROOT.name} at {pd.Timestamp.now(tz='America/New_York'):%Y-%m-%d %H:%M} ET")
    _run("REPO", section_repo)
    _run("DATA", lambda: section_data(args.hash))
    _run("SWITCHES AND CONFIG", section_switches)
    _run("PAPER BOOK", section_book)
    _run("RESEARCH", section_research)


if __name__ == "__main__":
    main()
