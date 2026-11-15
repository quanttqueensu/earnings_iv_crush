"""
test_preregistrations.py
Every recorded pre-registration hash still matches the shipped text, byte for byte.

A pre-registration is frozen by recording the SHA-256 of its text before any outcome is
viewed (``outputs/research/prereg_*.json``). The records name the file where it was written
at the time; the files now live under ``research/<line>/preregs/``. This test resolves each
recorded file by name, hashes it, and fails on any difference, so an edit to a frozen text,
or a line-ending conversion on checkout, cannot pass unnoticed. Studies started from
``research/_template/`` keep their text at ``research/<line>/<slug>/prereg.md``, where every
file shares a name, so a record whose path exists as written is resolved by that path.
"""

from __future__ import annotations

import ast
import hashlib
import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[1]
SHIPPED = {p.name: p for p in (ROOT / "research").glob("*/preregs/*.md")}


def _pairs(node: Any) -> Iterator[tuple[str, str]]:
    """Every (file, sha256) pair a hash record declares, however it is nested."""
    if isinstance(node, dict):
        f = node.get("prereg_file") or node.get("file")
        h = node.get("prereg_sha256") or node.get("sha256")
        if f and h:
            yield str(f), str(h)
        for key, value in node.items():
            if key.endswith("_file") and key != "prereg_file" and f"{key[:-5]}_sha256" in node:
                yield str(value), str(node[f"{key[:-5]}_sha256"])
            if isinstance(value, (dict, list)):
                yield from _pairs(value)
            elif isinstance(value, str) and value.startswith("[{"):
                yield from _pairs(ast.literal_eval(value))
    elif isinstance(node, list):
        for item in node:
            yield from _pairs(item)


RECORDS = sorted(
    {
        (rec.name, Path(f).as_posix(), h)
        for rec in (ROOT / "outputs" / "research").glob("prereg_*.json")
        for f, h in _pairs(json.loads(rec.read_text(encoding="utf-8")))
    }
)


def _run_log(record: str) -> list[dict[str, Any]]:
    """The run log ``verify_prereg`` keeps beside a record, oldest first; empty if none."""
    runs = ROOT / "outputs" / "research" / record.replace(".json", ".runs.jsonl")
    if not runs.is_file():
        return []
    lines = runs.read_text(encoding="utf-8").splitlines()
    return [json.loads(line) for line in lines if line.strip()]


def test_records_are_present() -> None:
    assert RECORDS, "no pre-registration hash records found under outputs/research"


@pytest.mark.parametrize(
    "record, name, sha", RECORDS, ids=[f"{r[0]}:{Path(r[1]).name}" for r in RECORDS]
)
def test_recorded_hash_matches_shipped_text(record: str, name: str, sha: str) -> None:
    as_written = ROOT / name
    if as_written.is_file() and "preregs" not in as_written.parts:
        path = as_written
    else:
        base = Path(name).name
        assert base in SHIPPED, f"{record} declares {base}, which is not under research/*/preregs"
        path = SHIPPED[base]
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    rec = json.loads((ROOT / "outputs" / "research" / record).read_text(encoding="utf-8"))
    if Path(str(rec.get("scorer_file", ""))).as_posix() != name or sha != rec.get("scorer_sha256"):
        assert digest == sha
        return
    # The scorer may change before outcomes are seen, as verify_prereg allows and logs; after an
    # unblinded run it must be byte-identical to the code that produced the outcomes.
    log = _run_log(record)
    unblinded = [e.get("scorer_sha256") for e in log if e.get("event") == "unblinded_run"]
    unblinded = [h for h in unblinded if h]
    if unblinded:
        assert digest == unblinded[-1]
        return
    changed = {e["scorer_sha256"] for e in log if e.get("event") == "code_change_pre_unblind"}
    assert digest in {sha} | changed
