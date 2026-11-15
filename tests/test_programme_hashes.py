"""
test_programme_hashes.py
Every script and note hash pinned by a research-programme freeze note still matches the bytes.

The exploratory programmes under ``outputs/research/`` freeze each held-out read by recording,
in a markdown note, the SHA-256 of the scorer, the modules it imports, its configuration and
often the note itself. The notes and scripts are versioned; the data files they also pin are
shared through the bucket and are absent from a checkout. This test parses the record formats
that name their target unambiguously (markdown tables, ``path: hash`` lines, ``sha256sum``
lines, JSON blocks, a hash wrapped onto the line after its file name, and the labelled
``<name>_sha256`` blocks whose labels the lane's freeze writer defines), resolves each target
relative to its note, and asserts that every pinned ``.py`` or ``.md`` file present in the
checkout hashes to the recorded value. Pins on data files, or on files not in the checkout,
are skipped. Self-hashing notes are checked under the exact convention each one uses, so an
edit to a frozen note or a line-ending conversion on checkout fails here.
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
RESEARCH = ROOT / "outputs" / "research"

# ── record grammar ──

_HEX = r"[0-9a-f]{64}"
_HEX_RE = re.compile(rf"(?<![0-9a-fA-F]){_HEX}(?![0-9a-fA-F])")
_EXT = "py|md|json|csv|parquet|log|xlsx|npz|txt|yaml|yml|pt|pkl|jsonl"
_PATH = rf"(?:\.\./)*[\w.-]+(?:/[\w.-]+)*\.(?:{_EXT})"
_PATH_RE = re.compile(rf"(?<![\w./*-])({_PATH})\b")

# A line that records the note's own hash. These never name a separate target.
_SELF_RE = re.compile(
    r"self[ _]?(?:sha|hash)|freeze_self_sha256|this note|note body sha|note sha-?256|"
    r"bytes above this line",
    re.IGNORECASE,
)
_TABLE_RE = re.compile(rf"^\|\s*`?({_PATH})`?[^|]*\|\s*`?({_HEX})`?\s*\|")
_JSON_RE = re.compile(rf'^\s*"({_PATH})":\s*"({_HEX})",?\s*$')
_SHASUM_RE = re.compile(rf"^\s*({_HEX})\s+\*?({_PATH})\b")
_LABEL_RE = re.compile(rf"^(\w+_sha256):\s*({_HEX})\s*$")
_WRAPPED_RE = re.compile(rf"^\s*`?({_HEX})`?[.,;]?\s*$")

# Labelled hash blocks name a role, not a file. The mapping is the one the lane's own freeze
# writer uses (write_freeze.py, addendum.py or score_heldout.py in the same folder); labels
# whose target is indirect or a data file are mapped too, so the funnel counts them.
LABEL_TARGETS: dict[str, dict[str, str]] = {
    "2026-11-14-slate-tests/L4-bayes/freeze_online_bayes.md": {
        "scorer_sha256": "score_heldout.py",
        "module_sha256": "../../../../earnings_iv_crush/research/online_bayes.py",
        "l4lib_sha256": "l4lib.py",
        "l4iter_sha256": "l4iter.py",
        "base_sha256": "../L1-corrections/base_corrected.parquet",
        "search_log_sha256": "search_log.csv",
    },
    "2026-11-15-deep-learning/D1-surface-net/freeze_D1.md": {
        "scorer_sha256": "score_heldout.py",
        "d1lib_sha256": "d1lib.py",
        "d1data_sha256": "d1data.py",
        "d1eval_sha256": "d1eval.py",
        "frozen_config_sha256": "frozen_config.json",
        "search_log_sha256": "search_log.csv",
    },
    "2026-11-15-deep-learning/D1-surface-net/freeze_D1_addendum.md": {
        "addendum_sha256": "addendum.py",
        "d1lib_sha256": "d1lib.py",
        "d1data_sha256": "d1data.py",
        "d1eval_sha256": "d1eval.py",
        "score_heldout_sha256": "score_heldout.py",
        "search_sha256": "search.py",
        "frozen_addendum_sha256": "frozen_addendum.json",
        "addendum_search_log_sha256": "addendum_search_log.csv",
    },
    "2026-11-14-earnings-adjacent-hunt/E2-informed-flow/freeze_2026-11-14_reversed_delta_flow.md": {
        "scorer_sha256": "score_heldout.py",
    },
}

_CODE_SUFFIXES = frozenset({".py", ".md"})

# Pinned pairs that do not match today and whose record explains why: {pair id: reason}.
KNOWN_MISMATCH: dict[str, str] = {}

# A pinned file edited after its freeze for a stated reason. The test undoes exactly that edit and
# requires the result to hash to the recorded value, so the exemption covers that edit and no
# other. {pair id: (reason, bytes added)}; the frozen text was CRLF, the committed text is LF.
_DL_TABULAR_GUARD = (
    b"# The lane folder is shared through the R2 bucket, not git, so a fresh clone skips these"
    b" tests.\n"
    b"if not LANE.exists():\n"
    b'    pytest.skip("lane D2 folder absent", allow_module_level=True)\n'
)
EXPLAINED_EDITS: dict[str, tuple[str, bytes]] = {
    "2026-11-15-deep-learning/D2-tabular/freeze_D2.md::../../../../tests/research/test_dl_tabular.py": (
        "a module-level skip guard added after the freeze so a clone without the lane folder skips "
        "these tests (PR #2 CI fix); the pin is context, not the D2 scorer",
        _DL_TABULAR_GUARD,
    ),
}


def _undo_edit(raw: bytes, added: bytes) -> bytes:
    """The frozen bytes: the added block removed, then the CRLF endings it was frozen with."""
    lf = raw.replace(b"\r\n", b"\n")
    assert lf.count(added) == 1, "the explained edit is no longer in the file as recorded"
    return lf.replace(added, b"").replace(b"\n", b"\r\n")


@dataclass(frozen=True)
class Pin:
    """One (file, sha256) pair recorded in a freeze note."""

    note: Path
    line: int
    target: str
    sha256: str
    fmt: str

    @property
    def pair_id(self) -> str:
        return f"{self.note.relative_to(RESEARCH).as_posix()}::{self.target}"

    def resolve(self) -> Path | None:
        """Return the first existing candidate path for the target, or None."""
        for base in (self.note.parent, self.note.parent / "scripts", ROOT):
            cand = (base / self.target).resolve()
            if cand.is_file():
                return cand
        # Older findings name pre-registrations by the file name they had under _private/;
        # the texts now live under research/<line>/preregs/ (see test_preregistrations.py).
        moved = list(ROOT.glob(f"research/*/preregs/{Path(self.target).name}"))
        return moved[0] if len(moved) == 1 else None


# ── parsing ──


def _notes() -> list[Path]:
    # Vendor documentation saved under raw/ carries content hashes that are not pins.
    return sorted(p for p in RESEARCH.rglob("*.md") if "raw" not in p.relative_to(RESEARCH).parts)


def _parse_note(note: Path) -> list[Pin]:
    lines = note.read_text(encoding="utf-8").splitlines()
    labels = LABEL_TARGETS.get(note.relative_to(RESEARCH).as_posix(), {})
    pins: list[Pin] = []
    for i, line in enumerate(lines):
        hexes = _HEX_RE.findall(line)
        if len(hexes) != 1:
            continue  # no hash, or several on one line (ambiguous pairing)
        sha = hexes[0]
        found: tuple[str, str] | None = None
        if m := _LABEL_RE.match(line):
            if m.group(1) in labels:
                found = (labels[m.group(1)], "label")
        elif _SELF_RE.search(line):
            continue
        elif m := _TABLE_RE.match(line):
            found = (m.group(1), "table")
        elif m := _JSON_RE.match(line):
            found = (m.group(1), "json")
        elif m := _SHASUM_RE.match(line):
            found = (m.group(2), "sha256sum")
        elif _WRAPPED_RE.match(line) and i > 0 and lines[i - 1].rstrip().endswith("SHA-256"):
            prev = _PATH_RE.findall(lines[i - 1])
            if len(prev) == 1:
                found = (prev[0], "wrapped")
        else:
            paths = _PATH_RE.findall(line)
            if len(paths) == 1:
                found = (paths[0], "inline")
        if found is not None:
            pins.append(Pin(note, i + 1, found[0], sha, found[1]))
    return pins


def _all_pins() -> list[Pin]:
    return [pin for note in _notes() for pin in _parse_note(note)]


PINS = _all_pins()

# ── self-hashing notes ──

_ZERO = "0" * 64


def _above(raw: bytes, start: int, sha: str) -> bytes:
    return raw[:start]


def _above_trimmed(raw: bytes, start: int, sha: str) -> bytes:
    # The writer hashed the body ending in one newline, then wrote a blank line before the hash.
    return raw[:start].rstrip(b"\n") + b"\n"


def _zeros_lf(raw: bytes, start: int, sha: str) -> bytes:
    # The scorer reads the note in text mode (newlines normalised) and blanks the hash.
    text = raw.decode("utf-8").replace("\r\n", "\n")
    return text.replace(sha, _ZERO).encode("utf-8")


def _pending(raw: bytes, start: int, sha: str) -> bytes:
    return raw.replace(sha.encode(), b"PENDING")


_CONVENTIONS: dict[str, Callable[[bytes, int, str], bytes]] = {
    "above": _above,
    "above_trimmed": _above_trimmed,
    "zeros_lf": _zeros_lf,
    "pending": _pending,
}

# {note: (marker that starts the self-hash line, convention)}. Each convention is the one the
# note states or its scorer implements, confirmed to reproduce the recorded hash exactly.
SELF_HASHED: dict[str, tuple[str, str]] = {
    "2026-11-13-niche-hunt/N05-treasuries-macro/freeze_N05_vxtlt.md": (
        "- this note, all lines above this one: ",
        "above",
    ),
    "2026-11-13-niche-hunt/N06-sofr-fomc/freeze_2026-11-13_fomc-variance-premium.md": (
        "Note body sha256: ",
        "above",
    ),
    "2026-11-13-niche-hunt/N08-index-macro-cached/freeze_2026-11-13_cpi-short-tenor-hedged-hold.md": (
        "SHA-256 of the bytes above this line: ",
        "above",
    ),
    "2026-11-13-niche-hunt/N10-crypto-scheduled/freeze_2026-11-13_monthly-expiry.md": (
        "Note SHA-256 (every line above this one): ",
        "above",
    ),
    "2026-11-13-niche-hunt/N11-forecastex-event-contracts/freeze_2026-11-13.md": (
        "Self hash: ",
        "above",
    ),
    "2026-11-13-niche-hunt/N12-metals-macro/freeze_heldout.md": (
        "SHA-256 of this note above this line: ",
        "above_trimmed",
    ),
    "2026-11-13-niche-hunt/N13-softs-ice/freeze_2026-11-13_wasde-event-variance.md": (
        "Self hash (SHA-256 of every line above this one): ",
        "above",
    ),
    "2026-11-13-niche-hunt/N15-adr-overnight-reporters/freeze_N15.md": (
        "SHA-256 of this note above this line: ",
        "above",
    ),
    "2026-11-13-niche-hunt/N16-country-etf-politics/freeze_heldout.md": (
        "SHA-256 of this note above this line: ",
        "above",
    ),
    "2026-11-14-earnings-adjacent-hunt/E1-gamma-scalp/freeze_2026-11-14_e1.md": (
        "note sha256: ",
        "above",
    ),
    "2026-11-14-earnings-adjacent-hunt/E2-informed-flow/freeze_2026-11-14_reversed_delta_flow.md": (
        "self_sha256: ",
        "zeros_lf",
    ),
    "2026-11-14-earnings-adjacent-hunt/E3-spillover/freeze_2026-11-14_spillover.md": (
        "- this note, with this value read as PENDING: note_sha256: ",
        "pending",
    ),
    "2026-11-14-earnings-adjacent-hunt/E4-expiry-mechanics/freeze_2026-11-14_oi-strike.md": (
        "SHA-256 of this note above this line: ",
        "above_trimmed",
    ),
    "2026-11-14-earnings-adjacent-hunt/E4-expiry-mechanics/freeze_2026-11-14_pinning.md": (
        "SHA-256 of this note above this line: ",
        "above_trimmed",
    ),
    "2026-11-14-earnings-adjacent-hunt/E5-literature-and-practice/freeze_e5_screens.md": (
        "note sha256: ",
        "above",
    ),
    "2026-11-14-earnings-adjacent-hunt/E5-literature-and-practice/freeze_session.md": (
        "note sha256: ",
        "above",
    ),
    "2026-11-14-slate-tests/L2-execution/freeze_b11_band.md": ("Self sha256 (", "above"),
    "2026-11-14-slate-tests/L2-execution/freeze_b1_auction.md": ("Self sha256 (", "above"),
    "2026-11-14-slate-tests/L2-execution/freeze_b2_mvdelta.md": ("Self sha256 (", "above"),
    "2026-11-14-slate-tests/L2-execution/freeze_b5_entry_minute.md": ("Self sha256 (", "above"),
    "2026-11-14-slate-tests/L2-execution/freeze_b6_expiry_choice.md": ("Self sha256 (", "above"),
    "2026-11-14-slate-tests/L2-execution/freeze_b8_strangle.md": ("Self sha256 (", "above"),
    "2026-11-14-slate-tests/L3-selection/freeze_c8.md": ("Note sha256 (", "above"),
    "2026-11-14-slate-tests/L3-selection/freeze_c8_addendum1.md": ("Note sha256 (", "above"),
    "2026-11-14-slate-tests/L4-bayes/freeze_online_bayes.md": ("self_sha256: ", "above"),
    "2026-11-15-deep-learning/D1-surface-net/freeze_D1.md": ("self_sha256: ", "above"),
    "2026-11-15-deep-learning/D1-surface-net/freeze_D1_addendum.md": ("self_sha256: ", "above"),
    "2026-11-15-deep-learning/D2-tabular/freeze_D2.md": ("freeze_self_sha256: ", "zeros_lf"),
}

# ── floors ──

# Parsed when this test was written: 150 pairs from 35 notes, 93 of them on .py/.md files, of
# which 93 resolve in the checkout. The floors sit a little below, so a parser regression that
# drops a format fails loudly.
MIN_PINS = 140
MIN_CODE_PINS_CHECKED = 85


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


# ── tests ──


@pytest.mark.parametrize("pin", PINS, ids=[p.pair_id for p in PINS])
def test_pinned_file_matches(pin: Pin) -> None:
    if Path(pin.target).suffix not in _CODE_SUFFIXES:
        pytest.skip(f"data file {pin.target}: shared through the bucket, not the checkout")
    path = pin.resolve()
    if path is None:
        pytest.skip(f"{pin.target} is not in this checkout")
    actual = _sha(path)
    if pin.pair_id in EXPLAINED_EDITS:
        _reason, added = EXPLAINED_EDITS[pin.pair_id]
        frozen = hashlib.sha256(_undo_edit(path.read_bytes(), added)).hexdigest()
        assert frozen == pin.sha256, f"{pin.target}: undoing the explained edit does not recover it"
        return
    if actual != pin.sha256 and pin.pair_id in KNOWN_MISMATCH:
        pytest.xfail(KNOWN_MISMATCH[pin.pair_id])
    assert actual == pin.sha256, (
        f"{path.relative_to(ROOT).as_posix()} changed after it was frozen in "
        f"{pin.note.relative_to(ROOT).as_posix()} line {pin.line} ({pin.fmt} format): "
        f"recorded {pin.sha256}, now {actual}"
    )


@pytest.mark.parametrize("note_rel", sorted(SELF_HASHED), ids=sorted(SELF_HASHED))
def test_self_hashing_note(note_rel: str) -> None:
    marker, convention = SELF_HASHED[note_rel]
    note = RESEARCH / note_rel
    if not note.is_file():
        pytest.skip(f"{note_rel} is not in this checkout")
    raw = note.read_bytes()
    start = raw.rfind(b"\n" + marker.encode()) + 1
    assert start > 0, f"self-hash line starting {marker!r} not found in {note_rel}"
    match = _HEX_RE.search(raw[start:].split(b"\n", 1)[0].decode("utf-8"))
    assert match, f"no SHA-256 on the self-hash line of {note_rel}"
    recorded = match.group(0)
    actual = hashlib.sha256(_CONVENTIONS[convention](raw, start, recorded)).hexdigest()
    assert actual == recorded, f"{note_rel} changed after it hashed itself ({convention})"


def test_parser_finds_pins() -> None:
    assert len(PINS) >= MIN_PINS, f"only {len(PINS)} pinned pairs parsed, expected {MIN_PINS}+"
    checked = [p for p in PINS if Path(p.target).suffix in _CODE_SUFFIXES and p.resolve()]
    assert len(checked) >= MIN_CODE_PINS_CHECKED, (
        f"only {len(checked)} .py/.md pins resolve in the checkout, "
        f"expected {MIN_CODE_PINS_CHECKED}+"
    )


def test_known_mismatches_are_current() -> None:
    ids = {p.pair_id for p in PINS}
    stale = sorted((set(KNOWN_MISMATCH) | set(EXPLAINED_EDITS)) - ids)
    assert not stale, f"KNOWN_MISMATCH names pairs the parser no longer finds: {stale}"
