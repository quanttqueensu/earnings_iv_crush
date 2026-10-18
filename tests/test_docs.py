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
