---
name: docforge-sdk-package
description: The standalone docforge-sdk uv package — a real installable client lib, sibling to mcp/bge_server, zero dep on docforge-rework
metadata:
  type: project
---

`src/docforge_sdk/` is a NEW standalone uv project: a typed async+sync Python client for the DocForge
REST API. Distribution name `docforge-sdk`, import package `docforge_sdk`.

**Why:** to give the MCP (and future consumers) one maintained, typed client instead of hand-rolled
httpx calls, and to keep it publishable to PyPI independently.

**How to apply / integration facts that make this package different from its siblings:**
- Unlike `src/mcp` and `src/bge_server` (`package = false`, run as scripts), this is a REAL package:
  `[build-system] hatchling`, `package` build, version read from `docforge_sdk/_version.py` via
  `[tool.hatch.version]`.
- It deliberately does NOT use `loggerplusplus`/`configplusplus` and has ZERO dependency on the
  `docforge-rework` tree — it must stay reusable standalone. Only deps: `httpx`, `pydantic`. Std
  `logging.getLogger("docforge_sdk")` is the sanctioned logger here (project.md's lpp rule is waived
  for this package).
- Consumed later by the MCP via a relative-path source; PyPI publish is a future step (metadata kept
  publish-ready).
- Architecture (the pattern P1 locked, P2 replicates per domain): `_requestspec.RequestSpec` (frozen
  dataclass, single source of URL/body) → `_transport.{Async,Sync}Transport` (share pure logic via
  `_TransportBase`; spec-execution + response-parsing written ONCE per transport, target model passed
  in) → `resources/<domain>.py` (`_<Domain>Specs` pure spec-builder mixin + `Async*`/`Sync*` shells
  differing only by `await`) → `client.{AsyncClient,Client}` wire resources onto a transport.
- `tests/openapi_snapshot.json` is committed (fetched live from `http://localhost:10040/openapi.json`)
  and drives `test_models_offline_parity.py` — diffs mirrored model schemas vs `components.schemas.*`.
- Verify gates all green: `uv run ruff check .`, `uv run mypy --strict docforge_sdk`, `uv run pytest`.
