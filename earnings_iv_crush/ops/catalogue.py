"""
catalogue.py
The results page: one line per study, rendered from ``research/catalogue.csv``.

Findings notes are spread over seven research lines, and most study folders hold a
pre-registration but not the verdict, which sits in a summary note or in
``docs/RESEARCH_STATE.md``. The catalogue gives every result one row (where it stands, how it was
produced, its headline and where the verdict lives), and this command renders the rows as
``docs/RESULTS.md``, which GitHub displays without the data bucket. ``--check`` validates the rows
against the tree and fails if the committed page is stale; ``tests/test_catalogue.py`` runs the
same checks in CI.

A row exists for every findings note (``research/<line>/findings/*.md`` and
``research/<line>/<YYYY-MM-DD-slug>/findings.md``) and for every dated study folder without a
``findings.md``. Lines are discovered from the folders, never listed here, so a new line cannot
be left off the page.

Usage
-----
    python -m earnings_iv_crush.ops.catalogue            # rewrite docs/RESULTS.md
    python -m earnings_iv_crush.ops.catalogue --check    # exit 1 on an invalid row or a stale page
"""

from __future__ import annotations

import argparse
import csv
import re
import sys
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from ..config import CATALOGUE, CatalogueConfig

ROOT = Path(__file__).resolve().parents[2]
COLUMNS = (
    "path",
    "line",
    "date",
    "kind",
    "status",
    "headline",
    "verdict_in",
    "artefacts",
    "superseded_by",
)
_DATED = re.compile(r"^\d{4}-\d{2}-\d{2}-")
_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_NONE = "-"


# ── rows ──────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Row:
    """One catalogue entry; every field is the CSV text as written."""

    path: str
    line: str
    date: str
    kind: str
    status: str
    headline: str
    verdict_in: str
    artefacts: str
    superseded_by: str


def load_rows(csv_path: Path) -> list[Row]:
    """Read the catalogue, refusing a header that is not exactly ``COLUMNS``."""
    with csv_path.open(encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        if tuple(reader.fieldnames or ()) != COLUMNS:
            raise ValueError(f"{csv_path}: header {reader.fieldnames} is not {list(COLUMNS)}")
        return [Row(**{c: (rec[c] or "").strip() for c in COLUMNS}) for rec in reader]


def expected_paths(root: Path) -> set[str]:
    """Every path the catalogue must carry: findings notes, and dated studies without one."""
    research = root / "research"
    notes = {p for p in research.glob("*/findings/*.md")}
    folders = [
        d
        for d in research.glob("*/*/")
        if d.is_dir() and _DATED.match(d.name) and not d.parent.name.startswith("_")
    ]
    notes |= {d / "findings.md" for d in folders if (d / "findings.md").is_file()}
    bare = {d for d in folders if not (d / "findings.md").is_file()}
    return {p.relative_to(root).as_posix() for p in notes | bare}


def _verdict_file(verdict_in: str) -> str:
    """The file part of a ``verdict_in`` cell, which may add `` section <heading>``."""
    return verdict_in.split(" section ", 1)[0].strip()


# ── validation ────────────────────────────────────────────────────────────────


def validate(rows: list[Row], root: Path, cfg: CatalogueConfig = CATALOGUE) -> list[str]:
    """Every problem with the rows, as readable messages; an empty list means valid."""
    errors: list[str] = []
    paths = [r.path for r in rows]
    dupes = sorted(p for p, n in Counter(paths).items() if n > 1)
    if dupes:
        errors.append(f"duplicate rows: {dupes}")
    expected = expected_paths(root)
    missing = sorted(expected - set(paths))
    extra = sorted(set(paths) - expected)
    if missing:
        errors.append(f"no catalogue row for: {missing}")
    if extra:
        errors.append(f"rows for paths that are not findings notes or study folders: {extra}")
    known = set(paths)
    for r in rows:
        where = f"{r.path}:"
        parts = r.path.split("/")
        if len(parts) < 3 or parts[0] != "research" or r.line != parts[1]:
            errors.append(f"{where} line {r.line!r} does not match the path")
        if not _DATE.match(r.date):
            errors.append(f"{where} date {r.date!r} is not YYYY-MM-DD")
        if r.kind not in cfg.kinds:
            errors.append(f"{where} kind {r.kind!r} not in {cfg.kinds}")
        if r.status not in cfg.statuses:
            errors.append(f"{where} status {r.status!r} not in {cfg.statuses}")
        if not r.headline or len(r.headline) > cfg.headline_max_chars:
            errors.append(f"{where} headline empty or over {cfg.headline_max_chars} characters")
        if "\n" in r.headline or "\u2014" in r.headline:
            errors.append(f"{where} headline holds a line break or an em dash")
        if r.verdict_in != _NONE and not (root / _verdict_file(r.verdict_in)).exists():
            errors.append(f"{where} verdict_in {r.verdict_in!r} does not exist")
        if r.verdict_in == _NONE and r.status != "open":
            errors.append(f"{where} has no verdict_in, so its status must be open")
        superseded = r.status == "superseded"
        if superseded != (r.superseded_by != _NONE):
            errors.append(f"{where} status superseded and superseded_by must come together")
        if r.superseded_by != _NONE and r.superseded_by not in known:
            errors.append(f"{where} superseded_by {r.superseded_by!r} is not a catalogue row")
        note = root / r.path
        if r.path.endswith(".md") and r.date >= cfg.header_required_from and note.is_file():
            head = note.read_text(encoding="utf-8").splitlines()[: cfg.header_lines]
            for marker in ("**Verdict:**", "**Reproduce:**"):
                if not any(line.lstrip().startswith(marker) for line in head):
                    errors.append(f"{where} has no {marker} line in its first {cfg.header_lines}")
    return errors


# ── rendering ─────────────────────────────────────────────────────────────────


def _cell(text: str) -> str:
    return text.replace("|", "\\|")


def _link(path: str, label: str) -> str:
    return f"[{_cell(label)}](../{path})"


def _label(path: str) -> str:
    name = Path(path).name
    if name == "findings.md":
        name = Path(path).parent.name
    return name.removesuffix(".md")


def _verdict_cell(r: Row) -> str:
    if r.verdict_in == _NONE:
        return "none recorded"
    file = _verdict_file(r.verdict_in)
    if file == r.path:
        return "this note"
    section = r.verdict_in[len(file) :].removeprefix(" section ").strip()
    text = _link(file, Path(file).name)
    return f"{text}, {_cell(section)}" if section else text


def render(rows: list[Row], cfg: CatalogueConfig = CATALOGUE) -> str:
    """The full text of ``docs/RESULTS.md``: counts by status, then one table per line."""
    counts = Counter(r.status for r in rows)
    out = [
        "# Results",
        "",
        "One line per study: where it stands, how it was produced, its headline and where the",
        "verdict is written. Generated from `research/catalogue.csv` by",
        "`python -m earnings_iv_crush.ops.catalogue`; edit the CSV, never this page.",
        "",
        "Headlines are condensed from each study's own verdict, with its N, interval and basis.",
        "Quote a number from the linked note, not from this page. Artefacts under",
        "`outputs/research/` are shared through the data bucket (`docs/DATA.md`), not git.",
        "",
        "| Status | Studies |",
        "|---|---|",
    ]
    out += [f"| {s} | {counts.get(s, 0)} |" for s in cfg.statuses]
    out += [f"| total | {len(rows)} |", ""]
    for line in sorted({r.line for r in rows}):
        out += [
            f"## {line}",
            "",
            "| Date | Status | Kind | Study | Headline | Verdict in | Artefacts |",
            "|---|---|---|---|---|---|---|",
        ]
        group = sorted(
            (r for r in rows if r.line == line), key=lambda r: (r.date, r.path), reverse=True
        )
        for r in group:
            status = r.status
            if r.superseded_by != _NONE:
                status = f"superseded by {_link(r.superseded_by, _label(r.superseded_by))}"
            art = f"`{r.artefacts}`" if r.artefacts != _NONE else ""
            out.append(
                f"| {r.date} | {status} | {r.kind} | {_link(r.path, _label(r.path))} "
                f"| {_cell(r.headline)} | {_verdict_cell(r)} | {art} |"
            )
        out.append("")
    return "\n".join(out)


# ── entry point ───────────────────────────────────────────────────────────────


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0] if __doc__ else None)
    ap.add_argument("--check", action="store_true", help="validate and compare; write nothing")
    args = ap.parse_args(argv)
    rows = load_rows(ROOT / CATALOGUE.csv_path)
    errors = validate(rows, ROOT)
    for e in errors:
        print(f"INVALID {e}")
    page = ROOT / CATALOGUE.page_path
    text = render(rows)
    if args.check:
        stale = not page.is_file() or page.read_text(encoding="utf-8") != text
        if stale:
            print(f"STALE {CATALOGUE.page_path}: run python -m earnings_iv_crush.ops.catalogue")
        print(f"{len(rows)} rows, {len(errors)} invalid, page {'stale' if stale else 'current'}")
        return 1 if errors or stale else 0
    if errors:
        print("not written: fix the rows first")
        return 1
    page.write_text(text, encoding="utf-8", newline="\n")
    print(f"wrote {CATALOGUE.page_path} from {len(rows)} rows")
    return 0


if __name__ == "__main__":
    sys.exit(main())
