---
name: inert-scaffolding-antipattern
description: Green tests + an unchanged golden on a claimed BEHAVIOR fix is a signal to grep for consumers, not a pass — a truncated agent ships config/fields/helpers with no wiring
metadata:
  type: reference
---

When reviewing a change that claims to fix runtime BEHAVIOR, "all tests pass + golden unchanged"
is NOT evidence of safety — it can be the *signature of an inert change*: nothing moved because
nothing is connected.

This actually happened twice this project: a pipeline agent got cut off mid-implementation and
left only scaffolding — new `extra=forbid` config fields never read, a dataclass field never set
or consumed, a helper function never called, docstrings describing logic that doesn't exist. The
suite stayed green (the logic had no callers to exercise) and the byte-golden stayed identical
(chunker config isn't serialized into the default blob), so both "safety" signals were vacuous.

**Heuristic:** for any claimed behavior fix, grep for the CONSUMER of every new symbol —
`ChunkRole.BOILERPLATE` assigned anywhere? the new config field read anywhere? the dataclass
field both SET and CONSUMED? the helper CALLED? If a symbol has no consumer, the fix is inert
regardless of green. Confirm with a real/behavioral test (or a live run) that asserts the OUTPUT
changed, not just that imports resolve. A truncated agent message ("Now add the …") is a red flag
that the wiring step never landed.
