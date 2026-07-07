# Archive — retired old-product artifacts

Everything here describes the **old DocForge product** (`src/docforge/`, the static `S0→S6` stage engine
with `common_libs`), superseded by the v2 graph engine in `src/docforge-rework/`. Preserved for history
and occasional reference — **not** loaded in normal sessions. See root `CLAUDE.md` for the current product.

| Path | What it is |
|---|---|
| `phases-legacy.md` | The old per-phase file inventory + key decisions (was `.claude/rules/phases.md`) |
| `rpi-legacy/dynamic-stage-architecture/` | RPI for the old dynamic self-describing stage system (replaced by the flow engine) |
| `rpi-legacy/pipeline-chain-policy/` | RPI for the old provider escalation chains (replaced by graph transitions) |
| `agent-memory-legacy/` | Retired agent memories about the old engine + stray `.claude` dirs that leaked under `src/` |

> When the old tree is deleted and `docforge-rework` is renamed to `docforge`, this archive can be
> trimmed or dropped entirely.
