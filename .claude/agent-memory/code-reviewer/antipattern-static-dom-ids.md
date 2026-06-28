---
name: antipattern-static-dom-ids
description: Hardcoded HTML id/htmlFor attributes silently break when a component renders more than once on the same screen
metadata:
  type: feedback
---

Components that hardcode a fixed DOM `id` (and a matching `<label htmlFor>`) are buggy
the moment they render more than once on the same page.

**Why:** the redesigned pipeline config renderer made `RecursiveFieldRenderer` render
ONE `GateLimits` (and one `FailurePolicyControl`) per chain+gate pair. The Enrich stage
has three pairs (classifier / ocr / vlm), so three `GateLimits` mount at once. `GateLimits`
hardcodes `id="gate-min-score"` / `id="gate-max-duration"` with matching `htmlFor`. Three
identical ids → clicking the OCR group's "Minimum quality score" label focuses the
Classifier group's input (browsers resolve `htmlFor` to the FIRST matching id). The data
writes are still correct (each `<input onChange>` closes over its own gate node.path), so
this is focus/a11y only, not config corruption — but it is a real regression exposed by
multi-instance rendering.

**How to apply:** when reviewing a component that can be rendered multiple times in a list
or loop, flag any static `id=`/`htmlFor=`. Require the id to be derived from a stable unique
key (e.g. the node's absolute `path`): `id={`gate-min-score-${node.path}`}`. Generally
suspect: forms/labels, `aria-controls`, `<input id>`, anchor targets.
