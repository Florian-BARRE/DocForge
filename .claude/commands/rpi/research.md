---
name: rpi:research
description: >-
  Research phase — gather technical context, docs, and constraints before implementing
  a DocForge feature. Produces a research brief that feeds into /rpi:plan.
model: sonnet
allowed-tools: ["WebSearch", "WebFetch", "Read", "Bash", "Agent"]
user-invocable: true
argument-hint: "<feature description>"
---

# RPI — Research Phase

Gather everything needed to design a new DocForge feature. Output a structured research
brief that the plan phase can consume directly.

## Steps

### 1. Understand the feature request

Read `$args` and identify:
- What DocForge pipeline stage(s) are involved (S0–S6)?
- What existing modules will be extended?
- What new dependencies or providers might be needed?

### 2. Read the spec and current state

```bash
# Check if the feature is mentioned in the spec
grep -n "$args" SPEC-docforge-document-intelligence-platform.md 2>/dev/null | head -20

# Identify affected source files
find src/docforge -name "*.py" | xargs grep -l "<relevant_keyword>" 2>/dev/null | head -20
```

### 3. Research external libraries (via docforge-researcher agent)

Spawn the `docforge-researcher` agent for any external library the feature will use.

### 4. Check constraints

- Is this feature gated by an env flag (S2_ENRICH_ENABLED pattern)?
- Does it require a new Alembic migration?
- Does it require a new provider Protocol?
- Does it require a new DAG node in `engine.py`?
- Does it require new endpoints in `backend/routers/`?

### 5. Output the research brief

```
FEATURE: <name>
STAGES AFFECTED: <S0/S1/S2/S4/S5/S6/engine/backend>
NEW FILES NEEDED:
  - src/docforge/libs/...
MODIFIED FILES:
  - src/docforge/libs/pipeline/engine.py
  - ...
NEW DEPENDENCIES: <uv add ...>
NEW ENV VARS: <VAR_NAME=default>
MIGRATION NEEDED: <yes/no — what schema change>
KEY CONSTRAINTS:
  - <constraint 1>
OPEN QUESTIONS:
  - <question 1>
```

Save the brief as `docs/rpi/<feature-slug>/research.md` for the plan phase.
