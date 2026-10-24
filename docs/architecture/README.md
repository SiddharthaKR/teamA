# System map

`graph.json` is the source of truth for the block-and-wire architecture page.

- Published page: https://claude.ai/artifact/2rciS2dP3EyiRcKvuYfixB (private; share it from the page's Share menu)
- Local copy: open `architecture.html` in a browser.

## Keeping it current

Whenever a module, dependency, tool or plan changes:

1. Edit `graph.json`: blocks (with `modules`, `tools`, `status`, `phase`, `decisions`), edges, and a `changelog` entry.
2. Run `python scripts/build_architecture_page.py`.
3. Run the tests. `tests/test_architecture_graph.py` fails when:
   - a module is missing from the map or listed twice;
   - a real import between blocks is not drawn, or a drawn `depends` wire no longer exists in the code;
   - the generated page is stale.
4. Republish `architecture_page.html` to the Artifact URL above.

Wire kinds: `depends` (Python import, test-checked), `implements` (adapter fulfils a port), `uses` / `calls` / `reads` / `stores` / `feeds` (runtime), `planned`.
