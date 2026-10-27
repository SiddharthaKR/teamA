#!/usr/bin/env python3
"""archmap: a block-and-wire architecture map kept honest against the code.

Single file, standard library only. Source of truth: docs/architecture/graph.json.

    python archmap.py init  --package mypkg --source-root src   # skeleton graph.json from the code
    python archmap.py scan                                     # what the code really imports
    python archmap.py check                                    # exit 1 if the map drifted
    python archmap.py build                                    # write the HTML page(s)

Options: --graph PATH (default docs/architecture/graph.json), --root PATH (project root,
default: current directory).

check (Python projects with "package" set) fails when a module is missing from the map
or listed twice, when a "depends" wire does not match a real import between blocks, or
when a third-party import is not declared as tech on the block that uses it. Projects in
other languages get the structural checks only.
"""

from __future__ import annotations

import argparse
import ast
from collections import defaultdict
import json
from pathlib import Path
import sys

VERSION = "archmap-1"
STATUSES = {"built", "planned", "on_hold"}
DEFAULT_ROWS = [
    ("actors", "People"), ("interface", "Interface"), ("application", "Application"),
    ("features", "Features"), ("contracts", "Contracts"), ("core", "Domain core"),
    ("adapters", "Adapters"), ("external", "External systems & data"), ("tooling", "Quality & dev tools"),
]


# --------------------------------------------------------------------------- code scan
def _module_name(path: Path, source_root: Path) -> str:
    parts = list(path.relative_to(source_root).with_suffix("").parts)
    if parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts)


def scan_python(root: Path, package: str, source_root: str = "src"):
    """Return (modules, internal_pairs, external) with module names relative to the package."""

    base = root / source_root
    pkg_dir = base / package.replace(".", "/")
    files = {}
    for path in sorted(pkg_dir.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        files[_module_name(path, base)] = path
    all_modules = set(files)

    def rel(name: str) -> str:
        return name[len(package) + 1:] if name.startswith(package + ".") else ("" if name == package else name)

    pairs: set[tuple[str, str]] = set()
    external: dict[str, set[str]] = defaultdict(set)
    meaningful: set[str] = set()
    stdlib = set(getattr(sys, "stdlib_module_names", ())) | {"__future__"}
    for module, path in files.items():
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        is_pkg = path.name == "__init__.py"
        has_code = any(not (isinstance(n, ast.Expr) and isinstance(getattr(n, "value", None), ast.Constant)) for n in tree.body)
        if not is_pkg or has_code:
            meaningful.add(module)
        for node in ast.walk(tree):
            targets: list[str] = []
            if isinstance(node, ast.Import):
                targets = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                if node.level:
                    anchor = module.split(".") if is_pkg else module.split(".")[:-1]
                    anchor = anchor[: len(anchor) - (node.level - 1)] if node.level > 1 else anchor
                    stem = ".".join(anchor + ([node.module] if node.module else []))
                else:
                    stem = node.module or ""
                candidates = [f"{stem}.{alias.name}" for alias in node.names]
                subs = [c for c in candidates if c in all_modules]
                targets = subs if subs and len(subs) == len(candidates) else [stem, *subs]
            for target in targets:
                if target == package or target.startswith(package + "."):
                    while target and target not in all_modules:
                        target = target.rpartition(".")[0]
                    if target and target != module:
                        pairs.add((rel(module), rel(target)))
                else:
                    top = target.split(".")[0]
                    if top and top not in stdlib:
                        external[top].add(rel(module))
    modules = {rel(m) for m in meaningful} - {""}
    pairs = {(a, b) for a, b in pairs if a in modules and b in modules}
    return modules, pairs, dict(external)


# --------------------------------------------------------------------------- checks
def load(graph_path: Path) -> dict:
    return json.loads(graph_path.read_text(encoding="utf-8"))


def check(graph_path: Path, root: Path) -> list[str]:
    graph = load(graph_path)
    problems: list[str] = []
    blocks = graph.get("blocks", [])
    ids = [b["id"] for b in blocks]
    by_id = {b["id"]: b for b in blocks}
    rows = {r["id"] for r in graph.get("rows", [])}
    tech_ids = {t["id"] for t in graph.get("tech", [])}
    if len(ids) != len(set(ids)):
        problems.append("duplicate block ids")
    for b in blocks:
        if b.get("row") not in rows:
            problems.append(f"block {b['id']} is in unknown row {b.get('row')}")
        if b.get("status") not in STATUSES:
            problems.append(f"block {b['id']} has status {b.get('status')}; use built, planned or on_hold")
        for t in b.get("tech", []):
            if t not in tech_ids:
                problems.append(f"block {b['id']} lists unknown tech {t}")
        if graph.get("package") and b.get("status") == "built" and b.get("kind", "code") == "code" and not b.get("modules"):
            problems.append(f"built code block {b['id']} names no modules")
    for e in graph.get("edges", []):
        if e["source"] not in by_id or e["target"] not in by_id:
            problems.append(f"wire {e['source']} -> {e['target']} has an unknown end")

    package = graph.get("package")
    if not package:
        return problems
    modules, pairs, external = scan_python(root, package, graph.get("source_root", "src"))
    owner: dict[str, str] = {}
    for b in blocks:
        for m in b.get("modules", []):
            if m in owner:
                problems.append(f"module {m} is in both {owner[m]} and {b['id']}")
            owner[m] = b["id"]
    for m in sorted(modules - set(owner)):
        problems.append(f"module {m} is not on the map")
    for m in sorted(set(owner) - modules):
        problems.append(f"map lists module {m}, which no longer exists")
    real = {(owner[a], owner[b]) for a, b in pairs if a in owner and b in owner and owner[a] != owner[b]}
    drawn = {(e["source"], e["target"]) for e in graph.get("edges", []) if e.get("kind") == "depends"}
    for s, t in sorted(real - drawn):
        problems.append(f"missing depends wire {s} -> {t} (the code imports it)")
    for s, t in sorted(drawn - real):
        problems.append(f"depends wire {s} -> {t} has no matching import")
    package_to_tech = {}
    for t in graph.get("tech", []):
        for p in t.get("packages", []):
            package_to_tech[p] = t["id"]
    for top, users in sorted(external.items()):
        tech = package_to_tech.get(top)
        if tech is None:
            problems.append(f"third-party import '{top}' (in {', '.join(sorted(users))}) is not declared in tech")
            continue
        for m in sorted(users):
            block = owner.get(m)
            if block and tech not in by_id[block].get("tech", []):
                problems.append(f"block {block} imports '{top}' ({m}) but does not list tech {tech}")
    return problems


# --------------------------------------------------------------------------- init / scan
def init(graph_path: Path, root: Path, package: str, source_root: str, name: str | None) -> None:
    if graph_path.exists():
        raise SystemExit(f"{graph_path} already exists")
    modules, pairs, external = scan_python(root, package, source_root)
    groups: dict[str, list[str]] = defaultdict(list)
    for m in sorted(modules):
        groups[m.split(".")[0]].append(m)
    blocks = [
        {"id": g.replace("_", "-"), "ref": f"U{i}", "label": g.replace("_", " ").title(), "row": "application",
         "status": "built", "kind": "code", "description": "TODO: what this part does.", "modules": mods,
         "tools": [], "tech": [], "decisions": []}
        for i, (g, mods) in enumerate(sorted(groups.items()), start=1)
    ]
    owner = {m: b["id"] for b in blocks for m in b["modules"]}
    edges = sorted({(owner[a], owner[b]) for a, b in pairs if owner[a] != owner[b]})
    tech = [{"id": top, "name": top, "category": "Library", "version": "", "license": "", "packages": [top], "notes": ""}
            for top in sorted(external)]
    for b in blocks:
        b["tech"] = sorted({top for top, users in external.items() if set(users) & set(b["modules"])})
    graph = {
        "name": name or package, "version": "", "package": package, "source_root": source_root,
        "artifact_url": "", "rows": [{"id": r, "label": l} for r, l in DEFAULT_ROWS],
        "blocks": blocks, "edges": [{"source": s, "target": t, "kind": "depends", "label": ""} for s, t in edges],
        "tech": tech, "decisions": {}, "changelog": [],
    }
    graph_path.parent.mkdir(parents=True, exist_ok=True)
    graph_path.write_text(json.dumps(graph, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"Wrote {graph_path}: {len(blocks)} blocks, {len(edges)} wires, {len(tech)} tech entries. Edit rows, labels and descriptions next.")


def scan(graph_path: Path, root: Path) -> None:
    graph = load(graph_path)
    modules, pairs, external = scan_python(root, graph["package"], graph.get("source_root", "src"))
    print(json.dumps({"modules": sorted(modules), "imports": sorted(pairs),
                      "third_party": {k: sorted(v) for k, v in sorted(external.items())}}, indent=1))


# --------------------------------------------------------------------------- build
def render_fragment(graph_path: Path) -> str:
    graph = load(graph_path)
    payload = json.dumps(graph, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    title = graph.get("title") or f"{graph.get('name', 'System')} Map"
    return TEMPLATE.replace("__TITLE__", title.replace("<", "")).replace("/*GRAPH_JSON*/", payload)


def render_standalone(fragment: str) -> str:
    return ('<!doctype html>\n<html lang="en">\n<head>\n<meta charset="utf-8">\n'
            '<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">\n'
            "</head>\n<body>\n" + fragment + "\n</body>\n</html>\n")


def build(graph_path: Path) -> tuple[Path, Path]:
    fragment = render_fragment(graph_path)
    page = graph_path.with_name("architecture_page.html")
    standalone = graph_path.with_name("architecture.html")
    page.write_text(fragment, encoding="utf-8")
    standalone.write_text(render_standalone(fragment), encoding="utf-8")
    return page, standalone


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Architecture map kept honest against the code.")
    parser.add_argument("command", choices=["init", "scan", "check", "build"])
    parser.add_argument("--graph", default="docs/architecture/graph.json")
    parser.add_argument("--root", default=".")
    parser.add_argument("--package")
    parser.add_argument("--source-root", default="src")
    parser.add_argument("--name")
    args = parser.parse_args(argv)
    root = Path(args.root).resolve()
    graph_path = (root / args.graph) if not Path(args.graph).is_absolute() else Path(args.graph)
    if args.command == "init":
        if not args.package:
            raise SystemExit("init needs --package")
        init(graph_path, root, args.package, args.source_root, args.name)
    elif args.command == "scan":
        scan(graph_path, root)
    elif args.command == "check":
        problems = check(graph_path, root)
        for p in problems:
            print("DRIFT:", p)
        print("map matches the code" if not problems else f"{len(problems)} problem(s)")
        raise SystemExit(1 if problems else 0)
    else:
        page, standalone = build(graph_path)
        print(f"Wrote {page} (publish this) and {standalone} (open locally)")


TEMPLATE = r'''<title>__TITLE__</title>
<meta name="claude:viewport-fit-sides" content="cover">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500&family=IBM+Plex+Sans:wght@400;500;600&display=swap">
<style>
/* Layout: a schematic sheet. Layers are bands in dependency order; blocks are parts with
   reference designators; wires are imports and runtime calls; a tech bill of materials follows. */
:root {
  --bg: #f2f5f4; --sheet: #fbfcfc; --panel: #ffffff; --ink: #17202a; --muted: #5a6571;
  --rule: #d7dedc; --dot: #cfd7d5; --band: #eef2f1; --wire: #7d8b98; --accent: #1f55c4;
  --accent-soft: rgba(31, 85, 196, .10); --built: #1d7a4b; --planned: #a86400; --hold: #858b95;
  --ext: #7a3fb0;
  --font-sans: "IBM Plex Sans", "Segoe UI", system-ui, sans-serif;
  --font-mono: "IBM Plex Mono", ui-monospace, "Cascadia Mono", Consolas, monospace;
}
@media (prefers-color-scheme: dark) { :root:not([data-theme="light"]) {
  --bg: #0f1419; --sheet: #121920; --panel: #17202a; --ink: #e5eaf0; --muted: #98a4b0;
  --rule: #26313c; --dot: #22303b; --band: #151d25; --wire: #64717f; --accent: #77a2ff;
  --accent-soft: rgba(119, 162, 255, .14); --built: #4fc58d; --planned: #e2a23e; --hold: #7b838d;
  --ext: #c49af0; color-scheme: dark; } }
:root[data-theme="dark"] {
  --bg: #0f1419; --sheet: #121920; --panel: #17202a; --ink: #e5eaf0; --muted: #98a4b0;
  --rule: #26313c; --dot: #22303b; --band: #151d25; --wire: #64717f; --accent: #77a2ff;
  --accent-soft: rgba(119, 162, 255, .14); --built: #4fc58d; --planned: #e2a23e; --hold: #7b838d;
  --ext: #c49af0; color-scheme: dark; }
body { background: var(--bg); color: var(--ink); font: 14px/1.5 var(--font-sans); }
.page { padding-left: max(16px, env(safe-area-inset-left, 0px)); padding-right: max(16px, env(safe-area-inset-right, 0px)); padding-block: 20px 40px; max-width: 1560px; margin: 0 auto; display: grid; gap: 16px; }
header { display: flex; flex-wrap: wrap; align-items: flex-end; justify-content: space-between; gap: 12px 24px; }
h1 { margin: 0; font-size: 22px; font-weight: 600; letter-spacing: -.01em; text-wrap: balance; }
.sub { color: var(--muted); font-family: var(--font-mono); font-size: 12px; }
.controls { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; }
.toggle { font: 500 12px var(--font-sans); color: var(--ink); background: var(--panel); border: 1px solid var(--rule); border-radius: 999px; padding: 5px 11px; cursor: pointer; display: inline-flex; gap: 6px; align-items: center; }
.toggle[aria-pressed="false"] { color: var(--muted); background: transparent; }
.toggle:focus-visible, .part:focus-visible, .chip:focus-visible, .tech-card:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }
.swatch { width: 10px; height: 10px; border-radius: 2px; display: inline-block; }
.layout { display: grid; grid-template-columns: minmax(0, 1fr) 300px; gap: 16px; align-items: start; }
@media (max-width: 1100px) { .layout { grid-template-columns: minmax(0, 1fr); } }
.scroller { overflow-x: auto; border: 1px solid var(--rule); border-radius: 6px; background: var(--sheet);
  background-image: radial-gradient(var(--dot) 1px, transparent 1px); background-size: 16px 16px; }
.canvas { position: relative; min-width: 1000px; padding: 12px 16px 16px; display: grid; gap: 10px; }
.wires { position: absolute; inset: 0; width: 100%; height: 100%; pointer-events: none; overflow: visible; }
.band { position: relative; display: grid; grid-template-columns: 96px minmax(0, 1fr); gap: 12px; align-items: stretch; }
.band-label { font: 500 11px var(--font-mono); text-transform: uppercase; letter-spacing: .08em; color: var(--muted); border-right: 1px dashed var(--rule); padding: 10px 8px 0 0; text-align: right; }
.parts { display: flex; flex-wrap: nowrap; gap: 12px; padding: 8px 0 18px; z-index: 1; }
.part { position: relative; z-index: 1; flex: 1 1 0; min-width: 0; max-width: 190px; text-align: left; font: inherit; color: var(--ink); background: var(--panel); border: 1.5px solid var(--rule); border-radius: 4px; padding: 8px 10px 9px; cursor: pointer; display: grid; gap: 3px; align-content: start; box-shadow: 0 1px 0 var(--rule); }
.part.wide { flex: 0 1 760px; max-width: 760px; }
.part .ref { font: 500 10.5px var(--font-mono); color: var(--muted); display: flex; justify-content: space-between; gap: 6px; }
.part .name { font-weight: 600; font-size: 13.5px; line-height: 1.25; overflow-wrap: anywhere; }
.part .meta { font: 11px var(--font-mono); color: var(--muted); overflow-wrap: anywhere; }
.part .tags { display: flex; flex-wrap: wrap; gap: 3px; }
.part .tag { font: 10.5px var(--font-mono); color: var(--ext); border: 1px solid currentColor; border-radius: 3px; padding: 0 4px; line-height: 16px; white-space: nowrap; max-width: 100%; overflow: hidden; text-overflow: ellipsis; }
.part.built { border-left: 4px solid var(--built); }
.part.planned { border-style: dashed; border-left: 4px dashed var(--planned); background: transparent; }
.part.on_hold { border-style: dashed; border-color: var(--hold); background: repeating-linear-gradient(135deg, transparent 0 6px, var(--band) 6px 12px); color: var(--muted); }
.part.actor, .part.external { border-radius: 14px; }
.part[aria-pressed="true"] { border-color: var(--accent); box-shadow: 0 0 0 3px var(--accent-soft); }
.part.dim { opacity: .35; }
.status { font: 500 10px var(--font-mono); text-transform: uppercase; letter-spacing: .06em; }
.status.built { color: var(--built); } .status.planned { color: var(--planned); } .status.on_hold { color: var(--hold); }
.panel { background: var(--panel); border: 1px solid var(--rule); border-radius: 6px; padding: 16px; display: grid; gap: 12px; position: sticky; top: calc(env(safe-area-inset-top, 0px) + 12px); min-width: 0; }
.panel h2 { margin: 0; font-size: 17px; font-weight: 600; text-wrap: balance; }
.panel p { margin: 0; }
.kv { display: grid; gap: 4px; }
.kv h3, .section-title { margin: 0; font: 500 11px var(--font-mono); text-transform: uppercase; letter-spacing: .08em; color: var(--muted); }
.mono-list { margin: 0; padding: 0; list-style: none; font: 12.5px var(--font-mono); display: grid; gap: 2px; overflow-wrap: anywhere; }
.chips { display: flex; flex-wrap: wrap; gap: 6px; }
.chip { font: 12px var(--font-sans); border: 1px solid var(--rule); background: transparent; color: var(--ink); border-radius: 4px; padding: 2px 8px; cursor: pointer; }
.chip.static { cursor: default; }
.chip.tech { color: var(--ext); border-color: currentColor; }
.hint { color: var(--muted); font-size: 13px; }
.box { background: var(--panel); border: 1px solid var(--rule); border-radius: 6px; padding: 14px 16px; display: grid; gap: 12px; }
.box h2 { margin: 0; font-size: 15px; font-weight: 600; }
.tech-groups { display: grid; gap: 14px; }
.tech-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(220px, 1fr)); gap: 10px; }
.tech-card { text-align: left; font: inherit; color: var(--ink); background: transparent; border: 1px solid var(--rule); border-left: 3px solid var(--ext); border-radius: 4px; padding: 8px 10px; cursor: pointer; display: grid; gap: 2px; min-width: 0; }
.tech-card[aria-pressed="true"] { border-color: var(--accent); box-shadow: 0 0 0 3px var(--accent-soft); }
.tech-card .tname { font-weight: 600; font-size: 13px; overflow-wrap: anywhere; }
.tech-card .tmeta { font: 11px var(--font-mono); color: var(--muted); overflow-wrap: anywhere; }
.tech-card .tnote { font-size: 12px; color: var(--muted); }
.tech-card.planned, .tech-card.on_hold { border-left-style: dashed; }
.log ol { margin: 0; padding: 0; list-style: none; display: grid; gap: 6px; }
.log li { display: grid; grid-template-columns: 92px 72px minmax(0, 1fr); gap: 10px; font-size: 13px; }
.log .when, .log .sha { font-family: var(--font-mono); color: var(--muted); font-size: 12px; }
@media (max-width: 560px) { .log li { grid-template-columns: minmax(0, 1fr); gap: 0; } }
path.wire { fill: none; stroke: var(--wire); stroke-width: 1.3; opacity: .75; transition: opacity .15s; }
path.wire.into-core { opacity: .28; }
path.wire.implements { stroke-dasharray: 2 3; }
path.wire.planned { stroke: var(--planned); stroke-dasharray: 6 4; opacity: .8; }
path.wire.runtime { stroke: var(--accent); opacity: .55; }
path.wire.hot { stroke: var(--accent); stroke-width: 2; opacity: 1; }
path.wire.faded { opacity: .07; }
@media (prefers-reduced-motion: reduce) { path.wire { transition: none; } }
</style>

<div class="page">
  <header>
    <div>
      <h1 id="title">System map</h1>
      <div class="sub" id="version"></div>
    </div>
    <div class="controls" role="group" aria-label="Show">
      <button class="toggle" id="t-planned" aria-pressed="true"><span class="swatch" style="border:1.5px dashed var(--planned)"></span>Planned</button>
      <button class="toggle" id="t-hold" aria-pressed="true"><span class="swatch" style="border:1.5px dashed var(--hold)"></span>On hold</button>
      <button class="toggle" id="t-core" aria-pressed="false"><span class="swatch" style="background:var(--wire)"></span>Imports into core</button>
      <button class="toggle" id="t-tags" aria-pressed="true"><span class="swatch" style="border:1.5px solid var(--ext)"></span>Tech tags</button>
    </div>
  </header>

  <div class="layout">
    <div class="scroller">
      <div class="canvas" id="canvas">
        <svg class="wires" aria-hidden="true">
          <defs>
            <marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse"><path d="M0 0L10 5L0 10z" fill="var(--wire)"/></marker>
            <marker id="arrow-hot" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse"><path d="M0 0L10 5L0 10z" fill="var(--accent)"/></marker>
            <marker id="arrow-planned" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse"><path d="M0 0L10 5L0 10z" fill="var(--planned)"/></marker>
          </defs>
          <g id="wire-layer"></g>
        </svg>
      </div>
    </div>
    <aside class="panel" id="panel" aria-live="polite"></aside>
  </div>

  <section class="box" aria-labelledby="tech-title">
    <h2 id="tech-title">External tech</h2>
    <p class="hint" id="tech-hint">Every third-party library, API, model, database and dataset the system relies on. Click one to highlight the parts that use it.</p>
    <div class="tech-groups" id="tech"></div>
  </section>

  <section class="box log" aria-labelledby="log-title">
    <h2 id="log-title">Design history</h2>
    <ol id="log"></ol>
  </section>
</div>

<script>
const GRAPH = /*GRAPH_JSON*/;
GRAPH.tech = GRAPH.tech || []; GRAPH.changelog = GRAPH.changelog || []; GRAPH.decisions = GRAPH.decisions || {};
for (const b of GRAPH.blocks) { b.modules = b.modules || []; b.tools = b.tools || []; b.tech = b.tech || []; b.decisions = b.decisions || []; b.kind = b.kind || "code"; }
const byId = Object.fromEntries(GRAPH.blocks.map(b => [b.id, b]));
const techById = Object.fromEntries(GRAPH.tech.map(t => [t.id, t]));
const rowIndex = Object.fromEntries(GRAPH.rows.map((r, i) => [r.id, i]));
const STATUS = { built: "Built", planned: "Planned", on_hold: "On hold" };
const RUNTIME = new Set(["uses", "calls", "reads", "stores", "feeds"]);
const CORE_ID = GRAPH.core_block || "core";
const state = { selected: null, tech: null, hover: null, planned: true, hold: true, core: false, tags: true };
const STORE = "archmap-view-" + (GRAPH.name || "");
try { const s = JSON.parse(localStorage.getItem(STORE) || "{}"); for (const k of ["planned", "hold", "core", "tags"]) if (k in s) state[k] = s[k]; } catch (e) {}

const canvas = document.getElementById("canvas");
const layer = document.getElementById("wire-layer");
const panel = document.getElementById("panel");
const esc = s => String(s ?? "").replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
document.getElementById("title").textContent = (GRAPH.name || "System") + " system map";
document.getElementById("version").textContent = GRAPH.version || "";

const els = {};
for (const row of GRAPH.rows) {
  const members = GRAPH.blocks.filter(x => x.row === row.id);
  if (!members.length) continue;
  const band = document.createElement("div");
  band.className = "band";
  band.innerHTML = `<div class="band-label">${esc(row.label)}</div><div class="parts"></div>`;
  const parts = band.querySelector(".parts");
  for (const b of members) {
    const el = document.createElement("button");
    el.type = "button";
    el.className = `part ${b.status} ${b.kind}` + (b.wide ? " wide" : "");
    el.setAttribute("aria-pressed", "false");
    el.dataset.id = b.id;
    const meta = b.wide && b.modules.length ? b.modules.map(m => m.split(".").pop()).join(" · ")
      : b.modules.length ? `${b.modules.length} module${b.modules.length > 1 ? "s" : ""}` : (b.phase || (b.kind === "code" ? "" : b.kind));
    const tags = b.tech.map(t => techById[t]).filter(Boolean);
    el.innerHTML = `<span class="ref"><span>${esc(b.ref)}</span><span class="status ${b.status}">${STATUS[b.status]}</span></span>
      <span class="name">${esc(b.label)}</span><span class="meta">${esc(meta)}</span>
      ${tags.length ? `<span class="tags">${tags.slice(0, 3).map(t => `<span class="tag">${esc(t.name)}</span>`).join("")}${tags.length > 3 ? `<span class="tag">+${tags.length - 3}</span>` : ""}</span>` : ""}`;
    el.addEventListener("click", ev => { ev.stopPropagation(); select(state.selected === b.id ? null : b.id); });
    el.addEventListener("mouseenter", () => { state.hover = b.id; paint(); });
    el.addEventListener("mouseleave", () => { state.hover = null; paint(); });
    parts.appendChild(el);
    els[b.id] = el;
  }
  canvas.appendChild(band);
}
canvas.addEventListener("click", () => select(null));

const visible = id => { const b = byId[id]; return !((b.status === "planned" && !state.planned) || (b.status === "on_hold" && !state.hold)); };
function edgeClass(e) {
  const c = ["wire"];
  if (e.kind === "planned") c.push("planned"); else if (e.kind === "implements") c.push("implements"); else if (RUNTIME.has(e.kind)) c.push("runtime");
  if (e.target === CORE_ID && e.kind === "depends") c.push("into-core");
  return c;
}

function render() {
  const base = canvas.getBoundingClientRect();
  const out = {}, inn = {};
  const shown = GRAPH.edges.filter(e => visible(e.source) && visible(e.target) && els[e.source] && els[e.target]);
  for (const e of shown) { (out[e.source] ||= []).push(e); (inn[e.target] ||= []).push(e); }
  const cx = id => { const r = els[id].getBoundingClientRect(); return r.left + r.width / 2; };
  for (const l of Object.values(out)) l.sort((a, b) => cx(a.target) - cx(b.target));
  for (const l of Object.values(inn)) l.sort((a, b) => cx(a.source) - cx(b.source));
  const slot = (list, e, id, side) => {
    const r = els[id].getBoundingClientRect(), n = list.length, i = list.indexOf(e);
    const span = Math.min(r.width * 0.7, n * 14);
    const x = r.left + r.width / 2 - span / 2 + (n === 1 ? span / 2 : (span * i) / (n - 1));
    return { x: x - base.left, y: (side === "top" ? r.top : r.bottom) - base.top };
  };
  layer.replaceChildren();
  const focus = state.selected, hov = state.hover;
  for (const e of shown) {
    if (e.target === CORE_ID && e.kind === "depends" && !state.core && ![e.source, CORE_ID].includes(focus) && ![e.source, CORE_ID].includes(hov)) continue;
    const sr = rowIndex[byId[e.source].row], tr = rowIndex[byId[e.target].row];
    const down = tr >= sr;
    const s = slot(out[e.source], e, e.source, down ? "bottom" : "top");
    const t = slot(inn[e.target], e, e.target, down ? "top" : "bottom");
    const d = tr === sr
      ? `M${s.x},${s.y} C${s.x},${s.y + 26} ${t.x},${t.y - 60} ${t.x},${t.y}`
      : `M${s.x},${s.y} C${s.x},${(s.y + t.y) / 2} ${t.x},${(s.y + t.y) / 2} ${t.x},${t.y}`;
    const p = document.createElementNS("http://www.w3.org/2000/svg", "path");
    p.setAttribute("d", d);
    p.dataset.source = e.source; p.dataset.target = e.target; p.dataset.kind = e.kind;
    for (const c of edgeClass(e)) p.classList.add(c);
    const title = document.createElementNS("http://www.w3.org/2000/svg", "title");
    title.textContent = `${byId[e.source].label} → ${byId[e.target].label}${e.label ? " (" + e.label + ")" : ""}`;
    p.appendChild(title);
    layer.appendChild(p);
  }
  paint();
}

function paint() {
  const focus = state.hover || state.selected;
  const techUsers = state.tech ? new Set(GRAPH.blocks.filter(b => b.tech.includes(state.tech)).map(b => b.id)) : null;
  for (const p of layer.querySelectorAll("path")) {
    const hot = focus && (p.dataset.source === focus || p.dataset.target === focus);
    p.classList.toggle("hot", !!hot);
    p.classList.toggle("faded", (!!focus && !hot) || (!!techUsers && !focus));
    p.setAttribute("marker-end", hot ? "url(#arrow-hot)" : p.dataset.kind === "planned" ? "url(#arrow-planned)" : "url(#arrow)");
  }
  const related = new Set();
  if (focus) for (const e of GRAPH.edges) { if (e.source === focus) related.add(e.target); if (e.target === focus) related.add(e.source); }
  for (const [id, el] of Object.entries(els)) {
    el.hidden = !visible(id);
    const dim = focus ? id !== focus && !related.has(id) : techUsers ? !techUsers.has(id) : false;
    el.classList.toggle("dim", dim);
    el.setAttribute("aria-pressed", String(id === state.selected || (!!techUsers && techUsers.has(id) && !focus)));
    const tags = el.querySelector(".tags"); if (tags) tags.hidden = !state.tags;
  }
  for (const card of document.querySelectorAll(".tech-card")) card.setAttribute("aria-pressed", String(card.dataset.tech === state.tech));
}

const blockChip = id => `<button class="chip" data-jump="${id}">${esc(byId[id].ref)} ${esc(byId[id].label)}</button>`;
const techChip = id => `<button class="chip tech" data-tech="${id}">${esc(techById[id]?.name || id)}</button>`;
function wirePanel() {
  for (const c of panel.querySelectorAll("[data-jump]")) c.addEventListener("click", () => {
    select(c.dataset.jump);
    els[c.dataset.jump].scrollIntoView({ block: "nearest", inline: "nearest", behavior: matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth" });
  });
  for (const c of panel.querySelectorAll("[data-tech]")) c.addEventListener("click", () => selectTech(c.dataset.tech));
}

function showPanel() {
  if (state.tech && !state.selected) {
    const t = techById[state.tech];
    const users = GRAPH.blocks.filter(b => b.tech.includes(t.id)).map(b => b.id);
    panel.innerHTML = `<div class="kv"><h3>${esc(t.category || "Tech")}</h3><h2>${esc(t.name)}</h2></div>
      <div class="chips">${t.version ? `<span class="chip static">${esc(t.version)}</span>` : ""}${t.license ? `<span class="chip static">${esc(t.license)}</span>` : ""}${t.status && t.status !== "built" ? `<span class="chip static status ${t.status}">${STATUS[t.status]}</span>` : ""}</div>
      ${t.notes ? `<p>${esc(t.notes)}</p>` : ""}
      ${(t.packages || []).length ? `<div class="kv"><h3>Imported as</h3><ul class="mono-list">${t.packages.map(p => `<li>${esc(p)}</li>`).join("")}</ul></div>` : ""}
      ${users.length ? `<div class="kv"><h3>Used by</h3><div class="chips">${users.map(blockChip).join("")}</div></div>` : ""}`;
    wirePanel(); return;
  }
  const id = state.selected;
  if (!id) {
    const counts = { built: 0, planned: 0, on_hold: 0 };
    for (const b of GRAPH.blocks) counts[b.status]++;
    panel.innerHTML = `<h2>How to read this map</h2>
      <p class="hint">Layers run top to bottom in dependency order; arrows point from the user of a part to the part it relies on. Click a part for its modules, functions, tech and wires.</p>
      <div class="kv"><h3>Parts</h3><p>${counts.built} built · ${counts.planned} planned · ${counts.on_hold} on hold · ${GRAPH.tech.length} external tech</p></div>
      <div class="kv"><h3>Wires</h3><p class="hint">Grey: code imports${GRAPH.package ? ", checked against the code" : ""}. Blue: runtime use. Dotted: implements a port. Amber dashes: planned.</p></div>
      ${GRAPH.rule ? `<div class="kv"><h3>The rule</h3><p class="hint">${esc(GRAPH.rule)}</p></div>` : ""}`;
    return;
  }
  const b = byId[id];
  const deps = [...new Set(GRAPH.edges.filter(e => e.source === id).map(e => e.target))];
  const users = [...new Set(GRAPH.edges.filter(e => e.target === id).map(e => e.source))];
  const changed = GRAPH.changelog.filter(c => (c.blocks || []).includes(id));
  panel.innerHTML = `
    <div class="kv"><h3>${esc(b.ref)} · ${esc(GRAPH.rows[rowIndex[b.row]].label)}</h3><h2>${esc(b.label)}</h2></div>
    <div class="chips"><span class="chip static status ${b.status}">${STATUS[b.status]}</span>${b.phase ? `<span class="chip static">${esc(b.phase)}</span>` : ""}${b.decisions.map(d => `<span class="chip static" title="${esc(GRAPH.decisions[d] || "")}">Decision ${esc(d)}</span>`).join("")}</div>
    <p>${esc(b.description)}</p>
    ${b.modules.length ? `<div class="kv"><h3>Modules</h3><ul class="mono-list">${b.modules.map(m => `<li>${esc(m)}</li>`).join("")}</ul></div>` : ""}
    ${b.tools.length ? `<div class="kv"><h3>Functions & tools</h3><ul class="mono-list">${b.tools.map(t => `<li>${esc(t)}</li>`).join("")}</ul></div>` : ""}
    ${b.tech.length ? `<div class="kv"><h3>External tech</h3><div class="chips">${b.tech.map(techChip).join("")}</div></div>` : ""}
    ${deps.length ? `<div class="kv"><h3>Relies on</h3><div class="chips">${deps.map(blockChip).join("")}</div></div>` : ""}
    ${users.length ? `<div class="kv"><h3>Used by</h3><div class="chips">${users.map(blockChip).join("")}</div></div>` : ""}
    ${changed.length ? `<div class="kv"><h3>Changed in</h3><ul class="mono-list">${changed.map(c => `<li>${esc(c.commit || "")} ${esc(c.title)}</li>`).join("")}</ul></div>` : ""}`;
  wirePanel();
}

function select(id) { state.selected = id; if (id) state.tech = null; showPanel(); render(); }
function selectTech(id) { state.tech = state.tech === id ? null : id; state.selected = null; showPanel(); render(); }

function bindToggle(btnId, key) {
  const btn = document.getElementById(btnId);
  btn.setAttribute("aria-pressed", String(state[key]));
  btn.addEventListener("click", () => {
    state[key] = !state[key];
    btn.setAttribute("aria-pressed", String(state[key]));
    try { localStorage.setItem(STORE, JSON.stringify({ planned: state.planned, hold: state.hold, core: state.core, tags: state.tags })); } catch (e) {}
    render();
  });
}
bindToggle("t-planned", "planned"); bindToggle("t-hold", "hold"); bindToggle("t-core", "core"); bindToggle("t-tags", "tags");

const ORDER = ["External API", "Model", "Framework", "Library", "Database", "Reference data", "Infrastructure", "Dev tool"];
const groups = {};
for (const t of GRAPH.tech) (groups[t.category || "Other"] ||= []).push(t);
const techRoot = document.getElementById("tech");
const cats = Object.keys(groups).sort((a, b) => (ORDER.indexOf(a) + 1 || 99) - (ORDER.indexOf(b) + 1 || 99));
techRoot.innerHTML = cats.map(cat => `<div class="kv"><div class="section-title">${esc(cat)}</div><div class="tech-grid">${
  groups[cat].map(t => {
    const n = GRAPH.blocks.filter(b => b.tech.includes(t.id)).length;
    return `<button class="tech-card ${esc(t.status || "built")}" data-tech="${esc(t.id)}" aria-pressed="false">
      <span class="tname">${esc(t.name)}</span>
      <span class="tmeta">${[t.version, t.license, n ? n + " part" + (n > 1 ? "s" : "") : ""].filter(Boolean).map(esc).join(" · ")}</span>
      ${t.notes ? `<span class="tnote">${esc(t.notes)}</span>` : ""}</button>`;
  }).join("")}</div></div>`).join("");
if (!GRAPH.tech.length) document.getElementById("tech-hint").textContent = "No external tech declared yet.";
for (const card of techRoot.querySelectorAll(".tech-card")) card.addEventListener("click", ev => { ev.stopPropagation(); selectTech(card.dataset.tech); });

document.getElementById("log").innerHTML = GRAPH.changelog.length ? GRAPH.changelog.map(c =>
  `<li><span class="when">${esc(c.date || "")}</span><span class="sha">${esc(c.commit || "")}</span><span>${esc(c.title)}</span></li>`).join("")
  : `<li class="hint">No entries yet.</li>`;

showPanel();
new ResizeObserver(() => render()).observe(canvas);
if (document.fonts && document.fonts.ready) document.fonts.ready.then(render);
render();
</script>
'''

if __name__ == "__main__":
    main()
