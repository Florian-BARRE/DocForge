---
name: shared-family-palette-scoping
description: The deliver family is shared across pipeline kinds; each facade must scope its palette view to its own kinds
metadata:
  type: project
---

The `deliver` family is deliberately SHARED across pipeline kinds: ingestion registers its terminal
kind `bundle` there, search registers its terminal kind `hits` there. It is the ONLY family shared
between `IngestPipeline.FAMILIES` and `SearchPipeline.FAMILIES`.

**Why:** `NodeRegistry.catalog(family)` returns every selectable kind of a family regardless of
pipeline kind, so a naive palette per-family leaks the other pipeline's terminal (search palette
showed `bundle`, ingest palette showed `hits`).

**How to apply:** each facade declares `FAMILY_KINDS: dict[str, set[str]]` (an allowlist for shared
families only) and passes `FAMILY_KINDS.get(family)` to `FamilyCatalog.from_family(family, kinds)`.
`from_family` filters node cards by kind when `kinds` is given, else lists all (unchanged for
`PipelineCatalog.palette`). Both default (`full=False`) and full palettes are scoped. If a NEW
family ever becomes shared between two pipeline kinds, add it to each facade's `FAMILY_KINDS` — the
palette view is the only place scoping is needed; the registry, build and run paths stay untouched.
