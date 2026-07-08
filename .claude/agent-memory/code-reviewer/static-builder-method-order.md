---
name: static-builder-method-order
description: Static builder classes in pipelines/ order methods public-build-first, deviating from python.md — how to grade consistently
metadata:
  type: feedback
---

The static-only builder classes under `shared/libs/pipelines/` (`EnrichBodyBuilder`,
`ChainFragmentBuilder`, the `*Helpers` classes, stage compilers) order their methods as:
`__new__` → public `build` → `__private` helpers (in call order). This deviates from
python.md's stated "dunder → __private → _protected → public" ordering.

Note the split: `build/builder.py` (`PipelineBuilder`) DOES follow python.md
(`__init__` → private `__build_*` → public `build`), while the sibling static builders
in the same tree put the public entry point first.

**Why:** the "public entry first, then the privates it calls, in call order" reading-order
is an established local pattern for these static builders — the public `build` is the one
method a reader wants first.

**How to apply:** flag this as LOW severity / informational, never blocking, and note that
it matches the surrounding static-builder convention. Do not demand a reorder in a pure
refactor whose sibling (e.g. `enrich_body.py`) already uses the same order. Only escalate
if the file mixes both orderings internally.
