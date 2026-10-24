"""Build the system map page from docs/architecture/graph.json.

    python scripts/build_architecture_page.py

Writes docs/architecture/architecture_page.html (the fragment published as the
Artifact) and docs/architecture/architecture.html (a standalone copy to open in
a browser). tests/test_architecture_graph.py fails if either is stale, and it
also fails if graph.json no longer matches the code's real imports.
"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs" / "architecture"


def render_fragment() -> str:
    graph = json.loads((DOCS / "graph.json").read_text(encoding="utf-8"))
    template = (DOCS / "template.html").read_text(encoding="utf-8")
    payload = json.dumps(graph, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    return template.replace("/*GRAPH_JSON*/", payload)


def render_standalone(fragment: str) -> str:
    return (
        '<!doctype html>\n<html lang="en">\n<head>\n<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">\n'
        "</head>\n<body>\n" + fragment + "\n</body>\n</html>\n"
    )


def main() -> None:
    fragment = render_fragment()
    (DOCS / "architecture_page.html").write_text(fragment, encoding="utf-8")
    (DOCS / "architecture.html").write_text(render_standalone(fragment), encoding="utf-8")
    print("Wrote docs/architecture/architecture_page.html and architecture.html")


if __name__ == "__main__":
    main()
