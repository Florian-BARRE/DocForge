---
name: pipeline-engine-edge-selection
description: FlowEngine now ranks outgoing edges by condition specificity (ScoreBelow>WhenEquals>OnSuccess/OnFailure>Always) before taking the first match; cross-rank ambiguity is FIXED, but SAME-rank fan-out is still order-dependent
metadata:
  type: project
---

UPDATED 2026-07-04 (rewrite/pipelines-node-engine). The engine (`shared/libs/pipelines/engine/core.py`, `FlowEngine.__next`) now SORTS a node's outgoing transitions by `__condition_rank` DESCENDING, then returns the first that matches. Ranks: `ScoreBelow=4 > WhenEquals=3 > OnSuccess/OnFailure=2 > Always=1`.

- **ScoreBelow escalation is now correct.** A low-score success satisfies both its `ScoreBelow` and its `OnSuccess`/`Always` edge, but ScoreBelow outranks so escalation fires first regardless of list order. The old order-dependence bug is RESOLVED. (PIPELINE.md §5 documents this priority.)
- **SAME-rank fan-out is STILL order-dependent.** Two `OnSuccess` edges (or two `WhenEquals`) from one node have equal rank; the stable sort keeps list order, so only the first-listed target runs — the other branch is silently dropped. PIPELINE.md line ~418 claims the validator rejects "fan-out ambigu"; when reviewing, VERIFY the validator actually rejects two equal-rank satisfiable out-edges (the WhenEquals switch relies on a single `OnSuccess` default edge as the else-branch, which is intended).

**How to apply:** still test any node with >1 outgoing edge. Cross-rank conflicts are safe now; focus on equal-rank duplicates and confirm the validator's fan-out check. Related: [[describe-reflection-fragility]], [[metagen-embed-node-traps]].
