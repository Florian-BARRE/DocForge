---
name: locality-empty-chain-nameerror
description: Latent NameError pattern — code after a for-loop referencing the loop variable crashes on empty iterable; seen+fixed in locality_checks embed.chain
metadata:
  type: project
---

Anti-pattern: a statement AFTER a `for x in seq:` loop that references the loop variable `x`. When
`seq` is empty the loop body never runs, `x` is never bound, and the trailing statement raises
`NameError` at runtime (Pydantic/static checks don't catch it).

**Seen & fixed:** `locality_checks.py::check_locality` had, after `for embed in pipeline.embed.chain:`,
a trailing duplicate `if LocalityChecks._is_remote_url(embed_url): issues.append(... "embed.provider" ...)`.
On an empty embed chain (no embed provider configured yet) this crashed config validation with
`NameError: embed_url`. The duplicate also emitted the same `locality.remote_embed` error on a
non-existent `embed.provider` field path. Removal is correct — the in-loop check (`embed.chain`)
covers every entry including the intended case.

**How to apply:** when reviewing a removed "dead block", verify (1) it was genuinely unreachable or
duplicate, (2) the surviving in-loop check covers the same intent, (3) nothing referenced the loop var
outside the loop. A removal that fixes a latent crash on the empty-collection path is a *correctness*
win, not just cleanup.

Related: [[extra_ignore_provider_field_removal]], [[search_pipeline_antipatterns]].
