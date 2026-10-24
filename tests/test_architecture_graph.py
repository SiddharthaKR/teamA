"""The architecture diagram (docs/architecture/graph.json) must match the code.

Every module belongs to exactly one block, and the block-level "depends" edges
are exactly the imports the code really has. Adding a module or a dependency
without updating the diagram fails this test, so the picture cannot drift.
"""

from pathlib import Path
import json
import sys

import grimp
import pytest

ROOT = Path(__file__).resolve().parents[1]
GRAPH = json.loads((ROOT / "docs" / "architecture" / "graph.json").read_text(encoding="utf-8"))
PACKAGE = GRAPH["package"]
PACKAGE_ROOTS = {"", "core", "features", "llm", "prompts", "schemas", "language"}


def _code_modules() -> set[str]:
    graph = grimp.build_graph(PACKAGE)
    modules = {m.removeprefix(PACKAGE).lstrip(".") for m in graph.modules if m.startswith(PACKAGE)}
    return modules - PACKAGE_ROOTS


def _module_to_block() -> dict[str, str]:
    owner: dict[str, str] = {}
    for block in GRAPH["blocks"]:
        for module in block["modules"]:
            assert module not in owner, f"{module} is in both {owner[module]} and {block['id']}"
            owner[module] = block["id"]
    return owner


def test_every_module_is_drawn_exactly_once() -> None:
    owner = _module_to_block()
    modules = _code_modules()

    assert modules - set(owner) == set(), "modules missing from the diagram"
    assert set(owner) - modules == set(), "diagram lists modules that no longer exist"


def test_depends_edges_are_exactly_the_real_imports() -> None:
    owner = _module_to_block()
    graph = grimp.build_graph(PACKAGE)
    real = set()
    for module in graph.modules:
        source = owner.get(module.removeprefix(PACKAGE).lstrip("."))
        for imported in graph.find_modules_directly_imported_by(module):
            target = owner.get(imported.removeprefix(PACKAGE).lstrip("."))
            if source and target and source != target:
                real.add((source, target))
    drawn = {(e["source"], e["target"]) for e in GRAPH["edges"] if e["kind"] == "depends"}

    assert real - drawn == set(), "imports missing from the diagram"
    assert drawn - real == set(), "diagram shows dependencies the code no longer has"


def test_edges_and_rows_are_consistent() -> None:
    ids = [block["id"] for block in GRAPH["blocks"]]
    rows = {row["id"] for row in GRAPH["rows"]}

    assert len(ids) == len(set(ids))
    assert {block["row"] for block in GRAPH["blocks"]} <= rows
    assert all(e["source"] in ids and e["target"] in ids for e in GRAPH["edges"])
    assert {block["status"] for block in GRAPH["blocks"]} <= {"built", "planned", "on_hold"}
    for block in GRAPH["blocks"]:
        if block["status"] == "built" and block["kind"] == "code":
            assert block["modules"], f"built code block {block['id']} names no modules"


def test_published_page_is_rebuilt_from_the_graph() -> None:
    sys.path.insert(0, str(ROOT / "scripts"))
    try:
        import build_architecture_page
    finally:
        sys.path.pop(0)
    expected = build_architecture_page.render_fragment()
    committed = (ROOT / "docs" / "architecture" / "architecture_page.html").read_text(encoding="utf-8")

    assert committed == expected, "run: python scripts/build_architecture_page.py"
