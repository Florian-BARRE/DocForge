# DocForge — Documentation Index

> Project overview, commands, and architecture live in the root **`CLAUDE.md`**.
> The full design spec is **`SPEC-docforge-document-intelligence-platform.md`**.

## Current (v2 rework — the active product)

- **`../src/docforge-rework/PIPELINE.md`** — THE pipeline reference (living doc): the 7 stages
  (INTAKE→PARSE→ENRICH→CHUNK→CONTEXTUALIZE→METAGEN→EMBED), every node, artefact, and decision.
- **`../.claude/rules/architecture.md`** — the graph-engine cheat-sheet (primitives, families, the 3 roots).

## Reference docs

| Doc | Scope |
|---|---|
| `metadata-architecture.md` | Metadata schema, field origins, filterable/lexical/semantic |
| `deployment-resources.md` | Per-service CPU/RAM ceilings & resource strategy |
| `api/` | REST surface notes — `collections`, `collections-config`, `discovery`, `capabilities` |

## Feature RPIs (research / plan / implement)

Design records for still-live components: `rpi/auth-keys-only/`, `rpi/bge-server-dynamic-batching/`,
`rpi/chunk-llm-metadata/`, `rpi/discovery-recursive/`.

## Archive

**`archive/`** — everything about the **retired old product** (`src/docforge/`, static S0→S6 engine):
`phases-legacy.md` (the old phase changelog), `rpi-legacy/` (superseded engine RPIs),
`agent-memory-legacy/` (retired agent memories). Kept for reference; never loaded in the daily path.
