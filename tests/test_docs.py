"""
test_docs.py
The documents stay navigable and never repeat a withdrawn figure.

* every markdown file that ships matches a row of ``docs/INDEX.md`` (one owner per question);
* every relative link in a current document resolves;
* no current document quotes a figure from the never-quote list (``docs/RESEARCH_STATE.md``
  section 4), which records each with the reason it is wrong;
* ``CLAUDE.md`` carries rules, not results: no signed decimals or percentages, which go stale.

Historical records (findings, pre-registrations, the dated reference documents) are exempt from
the figure and link checks: they are true as of their date and some cite paths that have since
moved, which ``docs/HISTORY.md`` maps.
"""

from __future__ import annotations

import fnmatch
import re
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
EXCLUDED_DIRS = {"_private", "outputs", "data", ".git", "paper", ".venv", "node_modules"}
HISTORICAL = ("research/*/preregs/*", "research/*/findings/*", "docs/reference/*")
NEVER_QUOTE = ("+2.04", "+0.115773", "+0.023504", "0.7611", "+0.096571", "0.85395")
LINK = re.compile(r"\]\(([^)#\s]+)(?:#[^)]*)?\)")


def _shipped_markdown() -> list[str]:
    """Markdown files git would publish: tracked or untracked-but-not-ignored."""
    try:
        out = subprocess.run(
            ["git", "ls-files", "--cached", "--others", "--exclude-standard", "*.md"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=True,
        ).stdout
        files = [f for f in out.splitlines() if f]
    except (OSError, subprocess.CalledProcessError):
        files = [p.relative_to(ROOT).as_posix() for p in ROOT.rglob("*.md")]
    # --cached still lists a tracked file whose deletion is not yet committed.
    return sorted(f for f in files if f.split("/")[0] not in EXCLUDED_DIRS and (ROOT / f).exists())


def _index_globs() -> list[str]:
    text = (ROOT / "docs" / "INDEX.md").read_text(encoding="utf-8")
    return re.findall(r"^\| `([^`]+)` \|", text, flags=re.MULTILINE)


def _matches(path: str, pattern: str) -> bool:
    if pattern.endswith("/**/*.md"):
        return path.startswith(pattern[: -len("**/*.md")]) and path.endswith(".md")
    return fnmatch.fnmatchcase(path, pattern) and path.count("/") == pattern.count("/")


DOCS = _shipped_markdown()
CURRENT = [d for d in DOCS if not any(fnmatch.fnmatchcase(d, h) for h in HISTORICAL)]


def test_every_markdown_file_has_an_owner_row() -> None:
    globs = _index_globs()
    orphans = [d for d in DOCS if not any(_matches(d, g) for g in globs)]
    assert not orphans, f"add rows to docs/INDEX.md for: {orphans}"


@pytest.mark.parametrize("doc", CURRENT)
def test_relative_links_resolve(doc: str) -> None:
    text = (ROOT / doc).read_text(encoding="utf-8")
    broken = []
    for target in LINK.findall(text):
        if re.match(r"^[a-z]+:", target) or target.startswith("<"):
            continue
        if not (ROOT / doc).parent.joinpath(target).resolve().exists():
            broken.append(target)
    assert not broken, f"{doc}: broken links {broken}"


@pytest.mark.parametrize("doc", [d for d in CURRENT if d != "docs/RESEARCH_STATE.md"])
def test_never_quote_figures_stay_out(doc: str) -> None:
    text = (ROOT / doc).read_text(encoding="utf-8")
    found = [f for f in NEVER_QUOTE if f in text]
    assert not found, f"{doc} quotes {found}; see docs/RESEARCH_STATE.md section 4"


def test_claude_md_holds_rules_not_results() -> None:
    text = (ROOT / "CLAUDE.md").read_text(encoding="utf-8")
    figures = re.findall(r"[+-]\d+\.\d+|\d+(?:\.\d+)?%", text)
    assert not figures, f"CLAUDE.md carries result-like figures {figures}; put them in docs/"


# ── the desk map lists exactly the desk ───────────────────────────────────────

DESK = ROOT / ".claude"
_DESK_SECTIONS = {
    "Hooks": ("hooks", "*.py", lambda p: p.name),
    "Rules": ("rules", "*.md", lambda p: p.name),
    "Skills": ("skills", "*/SKILL.md", lambda p: f"/{p.parent.name}"),
    "Agents": ("agents", "*.md", lambda p: p.stem),
}


def _desk_table(section: str) -> set[str]:
    """First-column names of the table under ``## <section>`` in ``.claude/README.md``."""
    text = (DESK / "README.md").read_text(encoding="utf-8")
    body = re.search(rf"^## {section}\n(.*?)(?=^## |\Z)", text, flags=re.MULTILINE | re.DOTALL)
    assert body, f".claude/README.md has no '## {section}' section"
    return set(re.findall(r"^\| `([^`]+)` \|", body.group(1), flags=re.MULTILINE))


@pytest.mark.parametrize("section", sorted(_DESK_SECTIONS))
def test_desk_map_lists_exactly_the_desk(section: str) -> None:
    folder, pattern, name = _DESK_SECTIONS[section]
    present = {name(p) for p in (DESK / folder).glob(pattern)}
    listed = _desk_table(section)
    assert present, f".claude/{folder} is empty; the desk walk found nothing"
    assert not present - listed, f".claude/README.md '{section}' omits {sorted(present - listed)}"
    assert (
        not listed - present
    ), f".claude/README.md '{section}' lists missing {sorted(listed - present)}"


# ── backticked repository paths in current documents exist ────────────────────

# Folders a pointer can start with. A path under the package may also be written relative to it
# (`research/protocol.py` for `earnings_iv_crush/research/protocol.py`), as docs/ARCHITECTURE.md
# does, so both readings are tried.
_TOPS = (
    "earnings_iv_crush/",
    "scripts/",
    "tests/",
    "research/",
    "docs/",
    "deploy/",
    ".claude/",
    ".github/",
)
_SPAN = re.compile(r"`([^`\s]+)`")
# Documents whose job is to name files that do not exist: what was removed, and what is planned.
_NAMES_ABSENT_FILES = ("docs/HISTORY.md", "docs/ROADMAP.md")
# Single absent paths a current document names on purpose, each with its reason.
KNOWN_ABSENT = {
    ".claude/settings.local.json": "personal settings, git-ignored by design",
    "scripts/reconcile_broker.py": "the T6 reconciliation job, ROADMAP B2, not yet built",
    "scripts/build_postea_calendar.py": "a lost builder, recorded in DATA_CATALOGUE gaps",
}


def _pointer(token: str) -> str | None:
    """The repository path a code span names, or None if it is not a checkable path."""
    path = token.split("::")[0].rstrip(".,;:)")
    if not path.startswith(_TOPS) or re.search(r"[*<>{}\[\]$]|YYYY|\.\.\.", path):
        return None
    return path.split(":")[0]


def _exists(path: str) -> bool:
    if (ROOT / path).exists() or (ROOT / "earnings_iv_crush" / path).exists():
        return True
    # A decision record is cited by number (`docs/decisions/0004`).
    return bool(list((ROOT / path).parent.glob((ROOT / path).name + "-*")))


@pytest.mark.parametrize("doc", [d for d in CURRENT if d not in _NAMES_ABSENT_FILES])
def test_backticked_paths_exist(doc: str) -> None:
    text = (ROOT / doc).read_text(encoding="utf-8")
    pointers = {p for p in map(_pointer, _SPAN.findall(text)) if p}
    broken = sorted(p for p in pointers if p not in KNOWN_ABSENT and not _exists(p))
    assert not broken, f"{doc} points at paths that do not exist: {broken}"
