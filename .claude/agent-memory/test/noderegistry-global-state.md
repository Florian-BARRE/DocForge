---
name: noderegistry-global-state
description: shared_libs.pipelines.registry.NodeRegistry is process-global — fake/test nodes must use a session-unique KIND string or the whole session crashes on collection.
metadata:
  type: project
---

`NodeRegistry.register(family)` raises `ValueError` on a duplicate `(family, kind)` pair —
and the registry is a class-level dict that persists for the lifetime of the Python process,
i.e. the WHOLE `pytest tests/units` session, across every test file.

**Rule applied throughout the suite**: every test-local fake/test node class gets a KIND
string prefixed with the test module's concern, e.g. `test_engine_producer`,
`test_foreach_extract`, `test_fev_classify`, `test_validation_producer`. Never reuse a bare
name like `"producer"` or `"extract"` across two test files — the second import will crash
the entire collection phase, not just that one test.

Real families/kinds already registered by `import shared_libs.pipelines.ingest.nodes` +
`import shared_libs.pipelines.nodes` (both idempotent — Python caches the import, the
`@register` decorators only fire once):

| family | kinds |
|---|---|
| `parser` | `docling` |
| `chunker` | `structure_aware`, `fixed_size`, `semantic` |
| `embed` | `bge_server`, `openai_compatible` |
| `ocr` | `rapidocr`, `mistral` |
| `vlm` | `openai_compatible` |
| `llm` | `mistral`, `openai_compatible` |
| `contextualize` | `breadcrumb`, `doc_meta`, `sliding`, `llm` |
| `metagen` | `chunk`, `document` |

`ContextualizerBreadcrumbNode` and `EmbedBgeServerNode` are `UNIQUE_IN_GRAPH=True` (singletons);
`ContextualizerLlmNode` and `MetagenChunkNode` are NOT (repeatable — e.g. two situating passes
at different scopes is legitimate). Check `.describe().unique_in_graph` before writing a test
that puts the same kind twice in one graph — [[stage-combinatorics-strategy]]'s stack-repeat
test hit this (breadcrumb twice fails validation; `llm` twice does not).

**Corollary hit while porting `tests/units/nodes/` (2026-07-05)**: any test that iterates
`NodeRegistry.families()`/`.kinds(...)` and asserts something about EVERY registered node (e.g.
`tests/units/api/test_design_surface.py`'s "zero mute field descriptions" check) MUST skip
`kind.startswith(("test_", "fake_"))` — throwaway fakes registered by other test modules under
real families (`deliver`, `ocr`, `vlm`, `enrich`, `metagen`, `embed`, `contextualize`) are picked
up too since the registry is process-global and collection order is alphabetical. No REAL node
kind is ever prefixed `test_`/`fake_`, so the filter is safe and won't hide a real regression.
