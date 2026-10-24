"""The system map (docs/architecture/graph.json) must match the code.

scripts/archmap.py check fails when a module is missing or listed twice, when a
"depends" wire does not match a real import, or when a third-party import is not
declared as tech on the block that uses it. The published page must be rebuilt.
"""

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
GRAPH = ROOT / "docs" / "architecture" / "graph.json"
sys.path.insert(0, str(ROOT / "scripts"))
import archmap  # noqa: E402

sys.path.pop(0)


def test_map_matches_the_code() -> None:
    assert archmap.check(GRAPH, ROOT) == []


def test_published_page_is_rebuilt_from_the_graph() -> None:
    committed = (GRAPH.parent / "architecture_page.html").read_text(encoding="utf-8")

    assert committed == archmap.render_fragment(GRAPH), "run: python scripts/archmap.py build"


def test_drift_is_detected(tmp_path: Path) -> None:
    import json

    graph = json.loads(GRAPH.read_text(encoding="utf-8"))
    graph["edges"] = [e for e in graph["edges"] if (e["source"], e["target"]) != ("gateway", "core")]
    for block in graph["blocks"]:
        if block["id"] == "openai":
            block["tech"] = []
    broken = tmp_path / "graph.json"
    broken.write_text(json.dumps(graph), encoding="utf-8")

    problems = archmap.check(broken, ROOT)

    assert any("missing depends wire gateway -> core" in p for p in problems)
    assert any("'requests'" in p for p in problems)
