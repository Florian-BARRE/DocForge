---
name: stray-claude-dir-under-src
description: Multi-agent feature batches can leave an agent-memory .claude dir written under src/ instead of repo-root — it is NOT gitignored and would be committed
metadata:
  type: feedback
---

When several agents (backend, frontend, …) collaborate on a feature and write their persistent
memory, watch for an agent writing to `src/docforge/.claude/agent-memory/<agent>/` instead of the
canonical repo-root `.claude/agent-memory/<agent>/`. Seen on the S5b metagen batch (2026-06-28):
`src/docforge/.claude/agent-memory/{backend,frontend}/*.md` appeared in the working tree.

**Why it matters:** `.gitignore` only covers the repo-root `.claude` patterns / `__pycache__`; a
`.claude` nested under `src/` is NOT ignored (`git check-ignore` returns nothing) so it would be
committed into the product source tree.

**How to apply:** in any review of a multi-agent batch, run `git status --short` and scan for a
`?? src/**/.claude/` entry. If present, flag as should-fix: move the useful memory content to the
repo-root `.claude/agent-memory/<agent>/` (merge into that agent's MEMORY.md index) and delete the
`src/**/.claude/` tree before commit. The memory files themselves are legitimate — only the location
is wrong. Related env-var hygiene gap: [[deletion_batch_residue]].
