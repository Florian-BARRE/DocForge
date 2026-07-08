---
name: coalesce-fragment-run-guard
description: Greedy "coalesce small groups" passes that guard only the incoming size (or only >= target) let a sub-target REAL unit absorb fragments — needs a fragment-run origin flag.
metadata:
  type: project
---

# Coalesce-small anti-pattern: guarding the incoming group is not enough

Seen in `structure_aware` chunker `__coalesce_small` (`shared/libs/pipelines/ingest/nodes/chunk/structure_aware/core.py`). Recurs in any "fold consecutive small items together up to a cap" pass.

**The trap.** A greedy pass folds a group into the open run when `incoming.tokens < min and running + incoming <= cap`. This guards only the *incoming* group's size. It does NOT stop a **real** unit (`min <= x < cap`) that was appended fresh from becoming the open run and then absorbing the next fragment. Result: a real/large-enough unit gets a tiny neighbour glued on — violating "only sub-min units coalesce". It is also order-dependent: `[real, tiny]` merges but `[tiny, real]` doesn't.

**Why it slips past review.** The docstring often claims protection only for groups `>= target/cap` (which the `running + x <= cap` check already gives for free), while the field/UI contract promises "only sub-min sections coalesce". The two disagree for the `min <= x < target` band, and the naive code matches the weaker docstring.

**Why tests miss it.** A fixture with tiny sections + one `> cap` giant section does NOT exercise the bug — the giant is trivially protected by the cap check. The discriminating case is a **mid-size real unit (`min <= x < target`) immediately followed by a tiny one**; assert the real unit keeps its own `block_ids` (nothing appended).

**Fix.** Track whether the open run was *started by a fragment* (`tail_is_fragment_run = tokens < min`). Only fold when `tail_is_fragment_run and incoming < min and running + incoming <= cap`. This still lets a fragment-run keep growing past min toward target, but never lets a real unit be a fold target.

**Also check when reviewing these passes:** stale Code Summary / `HOW_IT_WORKS` / field descriptions (contract-locked UI text) that still describe the pre-relaxation behavior; and overlap/seed interaction — folding a seeded group back into the neighbour its seed was copied from double-counts passages (usually unreachable because seeded groups are ~target-sized, but flag under degenerate `target <= min`).
