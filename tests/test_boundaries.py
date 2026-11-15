"""
test_boundaries.py
Research code cannot reach the order path, and the order path does not import research studies.

Only ``earnings_iv_crush/live/`` (and the paper-book drivers and probes under ``scripts/`` and
``deploy/``) may talk to the broker. The broker modules are derived from the code, not listed:
every ``live/`` module that imports the IB client library, and every ``live/`` module that imports
one of those. Everything on the research side, the studies under ``research/``, the programme
scripts under ``outputs/research/``, the data builders under ``scripts/build/`` and every package
module outside ``live/``, must not import a broker
module or the IB client library, nor name an order method. Reading the paper book's stores
(``live/order_events.py``, ``live/paper_book.py``), as ``ops/orient.py`` does, stays allowed.
In the other direction, ``live/`` must not import the top-level ``research`` package, whose
closed studies are frozen and unreviewed for trading use.

The modules are parsed, never imported, so the test runs offline and executes nothing.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "earnings_iv_crush"

IB_LIBRARIES = ("ib_async", "ib_insync")
# ib_async / ib_insync methods that send, modify or cancel an order.
ORDER_METHODS = frozenset({"placeOrder", "cancelOrder", "reqGlobalCancel", "bracketOrder"})


def _research_side() -> list[Path]:
    files = [*(ROOT / "research").rglob("*.py"), *(ROOT / "scripts" / "build").rglob("*.py")]
    files += [*(ROOT / "outputs" / "research").rglob("*.py")]
    files += [p for p in PACKAGE.rglob("*.py") if "live" not in p.relative_to(PACKAGE).parts]
    return sorted(p for p in files if "__pycache__" not in p.parts)


def _imports(tree: ast.AST, path: Path) -> set[str]:
    """Absolute dotted names of every module a file imports, relative imports resolved."""
    names: set[str] = set()
    package = ".".join(path.relative_to(ROOT).with_suffix("").parts[:-1])
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names |= {a.name for a in node.names}
        elif isinstance(node, ast.ImportFrom):
            base = node.module or ""
            if node.level:
                parent = package.split(".")[: len(package.split(".")) - node.level + 1]
                base = ".".join([*parent, base] if base else parent)
            names.add(base)
            names |= {f"{base}.{a.name}" for a in node.names}
    return names


def _names(tree: ast.AST) -> set[str]:
    out: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute):
            out.add(node.attr)
        elif isinstance(node, ast.Name):
            out.add(node.id)
    return out


def _parse(path: Path) -> ast.AST:
    # utf-8-sig: some programme scripts were saved with a byte-order mark.
    return ast.parse(path.read_text(encoding="utf-8-sig"), filename=str(path))


def _hits(imports: set[str], prefixes: tuple[str, ...]) -> list[str]:
    return sorted(n for n in imports if any(n == p or n.startswith(p + ".") for p in prefixes))


def _module_name(path: Path) -> str:
    rel = path.relative_to(ROOT).with_suffix("").parts
    return ".".join(rel[:-1] if rel[-1] == "__init__" else rel)


def broker_modules() -> tuple[str, ...]:
    """``live/`` modules that reach the IB client library, directly or through each other."""
    live = {
        _module_name(p): _imports(_parse(p), p)
        for p in (PACKAGE / "live").rglob("*.py")
        if "__pycache__" not in p.parts
    }
    broker = {m for m, imps in live.items() if _hits(imps, IB_LIBRARIES)}
    grew = True
    while grew:
        more = {m for m, imps in live.items() if m not in broker and _hits(imps, tuple(broker))}
        broker |= more
        grew = bool(more)
    return tuple(sorted(broker))


RESEARCH_SIDE = _research_side()
BROKER = broker_modules()
FORBIDDEN_MODULES = (*BROKER, *IB_LIBRARIES)


def test_research_side_is_found() -> None:
    assert len(RESEARCH_SIDE) > 50, "the research-side file walk found almost nothing"


def test_broker_modules_are_found() -> None:
    assert "earnings_iv_crush.live.ib_orders" in BROKER
    assert "earnings_iv_crush.live.ib_connection" in BROKER
    assert "earnings_iv_crush.live" not in BROKER, "importing the live package must stay safe"


@pytest.mark.parametrize(
    "path", RESEARCH_SIDE, ids=[p.relative_to(ROOT).as_posix() for p in RESEARCH_SIDE]
)
def test_research_side_cannot_reach_the_order_path(path: Path) -> None:
    tree = _parse(path)
    bad = _hits(_imports(tree, path), FORBIDDEN_MODULES)
    assert not bad, f"{path.relative_to(ROOT)} imports {bad}"
    orders = sorted(_names(tree) & ORDER_METHODS)
    assert not orders, f"{path.relative_to(ROOT)} names order methods {orders}"


def test_live_does_not_import_research_studies() -> None:
    offenders = {}
    for path in sorted((PACKAGE / "live").rglob("*.py")):
        bad = _hits(_imports(_parse(path), path), ("research",))
        if bad:
            offenders[path.relative_to(ROOT).as_posix()] = bad
    assert not offenders, f"the order path imports frozen studies: {offenders}"


def test_relative_imports_resolve_to_the_package() -> None:
    path = PACKAGE / "research" / "example.py"
    tree = ast.parse("from ..live import ib_orders, paper_book\nfrom . import protocol\n")
    imports = _imports(tree, path)
    assert "earnings_iv_crush.live.ib_orders" in imports
    assert "earnings_iv_crush.research.protocol" in imports
    # The store is allowed; the broker module is not.
    assert _hits(imports, FORBIDDEN_MODULES) == ["earnings_iv_crush.live.ib_orders"]
