---
name: stages-method-order
description: shared_libs pipelines/ingest/stages static builder classes order methods public-entrypoint-first, not python.md's dunder→private→public
metadata:
  type: feedback
---

In `shared/libs/pipelines/ingest/stages/` the static builder/reader classes
(`IngestAssembler`, `SegmentBuilder`, `ContextualizeStack`, `StageCompiler`,
`StateReader`, `ContextualizeReader`, `StageView` builders, etc.) consistently place
the PUBLIC entry classmethod first (`assemble` / `all` / `positions` / `apply` / `read` /
`stack`), then the `__private` helpers below it.

This inverts python.md's stated method order (dunder → `__private` → `_protected` → public).

**Why:** it is a deliberate, package-wide convention — the public "front door" reads first,
top-down, before the helpers it calls. It is not an accident introduced by any single phase.

**How to apply:** do NOT raise this as a rule violation when reviewing files in this package.
It would be noise the owner has already decided against. Only flag method order if a file
breaks its OWN local convention (mixes both styles inconsistently).
