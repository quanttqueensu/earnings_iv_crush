"""
test_catalogue.py
The results catalogue covers every study, and the page rendered from it is current.

``research/catalogue.csv`` carries one row per findings note and per dated study folder without a
findings note (``earnings_iv_crush/ops/catalogue.py``). These tests fail when a study is added
without its row, when a row points at nothing, and when ``docs/RESULTS.md`` was not re-rendered
after the CSV changed. The synthetic tree checks that each validation fails loudly on its own.
"""

from __future__ import annotations

import csv
from pathlib import Path

import pytest

from earnings_iv_crush.config import CATALOGUE
from earnings_iv_crush.ops import catalogue as cat

ROOT = Path(__file__).resolve().parents[1]


# ── the shipped catalogue ─────────────────────────────────────────────────────


def test_shipped_catalogue_is_valid() -> None:
    rows = cat.load_rows(ROOT / CATALOGUE.csv_path)
    errors = cat.validate(rows, ROOT)
    assert not errors, "\n".join(errors)


def test_results_page_is_current() -> None:
    rows = cat.load_rows(ROOT / CATALOGUE.csv_path)
    page = (ROOT / CATALOGUE.page_path).read_text(encoding="utf-8")
    assert page == cat.render(rows), "run: python -m earnings_iv_crush.ops.catalogue"


# ── a synthetic tree ──────────────────────────────────────────────────────────


def _tree(tmp_path: Path) -> Path:
    for rel in (
        "research/alpha/findings/old_note.md",
        "research/alpha/2026-01-02-study-a/prereg.md",
        "research/alpha/2026-01-03-study-b/findings.md",
        "research/_template/2026-01-01-template/prereg.md",
    ):
        (tmp_path / rel).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / rel).write_text("x\n", encoding="utf-8")
    return tmp_path


def _row(path: str, **over: str) -> cat.Row:
    base = {
        "path": path,
        "line": "alpha",
        "date": "2026-01-02",
        "kind": "preregistered",
        "status": "closed",
        "headline": "Selected book below the matched null, N=40, per trade, net at the touch.",
        "verdict_in": path if path.endswith(".md") else "research/alpha/findings/old_note.md",
        "artefacts": "-",
        "superseded_by": "-",
    }
    base.update(over)
    return cat.Row(**base)


def _valid_rows() -> list[cat.Row]:
    return [
        _row("research/alpha/findings/old_note.md"),
        _row("research/alpha/2026-01-02-study-a"),
        _row("research/alpha/2026-01-03-study-b/findings.md", date="2026-01-03"),
    ]


def test_expected_paths_cover_notes_and_bare_study_folders(tmp_path: Path) -> None:
    root = _tree(tmp_path)
    assert cat.expected_paths(root) == {
        "research/alpha/findings/old_note.md",
        "research/alpha/2026-01-02-study-a",
        "research/alpha/2026-01-03-study-b/findings.md",
    }


def test_valid_rows_pass(tmp_path: Path) -> None:
    assert cat.validate(_valid_rows(), _tree(tmp_path)) == []


@pytest.mark.parametrize(
    "change, message",
    [
        ({"status": "won"}, "status"),
        ({"kind": "vibes"}, "kind"),
        ({"date": "2026-1-2"}, "date"),
        ({"line": "beta"}, "line"),
        ({"headline": "x" * (CATALOGUE.headline_max_chars + 1)}, "headline"),
        ({"headline": "a \u2014 b"}, "em dash"),
        ({"verdict_in": "research/alpha/findings/missing.md"}, "verdict_in"),
        ({"verdict_in": "-"}, "must be open"),
        ({"status": "superseded"}, "superseded"),
        ({"superseded_by": "research/alpha/nowhere"}, "superseded"),
    ],
)
def test_each_bad_field_is_reported(tmp_path: Path, change: dict[str, str], message: str) -> None:
    rows = _valid_rows()
    rows[0] = _row(rows[0].path, **change)
    errors = cat.validate(rows, _tree(tmp_path))
    assert any(message in e for e in errors), errors


def test_a_study_without_a_row_is_reported(tmp_path: Path) -> None:
    errors = cat.validate(_valid_rows()[:2], _tree(tmp_path))
    assert any("no catalogue row" in e and "study-b" in e for e in errors), errors


def test_a_duplicate_row_is_reported(tmp_path: Path) -> None:
    rows = _valid_rows()
    errors = cat.validate([*rows, rows[0]], _tree(tmp_path))
    assert any("duplicate" in e for e in errors), errors


def test_a_new_note_needs_the_verdict_and_reproduce_lines(tmp_path: Path) -> None:
    root = _tree(tmp_path)
    rows = _valid_rows()
    path = rows[2].path
    rows[2] = _row(path, date=CATALOGUE.header_required_from)
    errors = cat.validate(rows, root)
    assert any("**Verdict:**" in e for e in errors) and any("**Reproduce:**" in e for e in errors)
    (root / path).write_text(
        "# Study b\n\n**Verdict:** closed, N=40.\n\n**Reproduce:**\n\n    python study.py\n",
        encoding="utf-8",
    )
    assert cat.validate(rows, root) == []


def test_a_wrong_header_is_refused(tmp_path: Path) -> None:
    path = tmp_path / "catalogue.csv"
    with path.open("w", encoding="utf-8", newline="") as fh:
        csv.writer(fh).writerow(["path", "status"])
    with pytest.raises(ValueError, match="header"):
        cat.load_rows(path)


def test_render_groups_by_line_and_escapes_pipes() -> None:
    rows = [
        *_valid_rows(),
        _row("research/beta/findings/n.md", line="beta", headline="a | b"),
    ]
    page = cat.render(rows)
    assert page.index("## alpha") < page.index("## beta")
    assert "a \\| b" in page
    assert "| total | 4 |" in page
    # Newest first within a line.
    assert page.index("study-b") < page.index("study-a")
