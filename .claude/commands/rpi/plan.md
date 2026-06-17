---
name: rpi:plan
description: >-
  Plan phase — design the implementation approach for a DocForge feature based on
  a research brief from /rpi:research. Produces a step-by-step plan with GO/NO-GO gate.
model: opus
allowed-tools: ["Read", "Bash", "Agent"]
user-invocable: true
argument-hint: "<feature-slug or path to research.md>"
---

# RPI — Plan Phase

Design a concrete implementation plan for a DocForge feature. Requires a research brief
(from `/rpi:research`) or a feature description in `$args`.

## Steps

### 1. Load research brief

```bash
cat docs/rpi/$args/research.md 2>/dev/null || echo "No brief found — using $args directly"
```

### 2. Design the implementation

For each new file or modification:
- What class/function is added?
- What interface does it implement?
- What are the dependencies and injection points?
- What is the test strategy?

### 3. Validate against DocForge invariants

- [ ] IR remains canonical — feature doesn't create a new source of truth
- [ ] Provider is behind a Protocol interface
- [ ] New env flag added (disable by default for safety)
- [ ] Alembic migration planned if schema changes
- [ ] DAG node planned in `engine.py` if new stage
- [ ] No Docker/MinIO references

### 4. GO / NO-GO gate

Present the plan and ask:
```
Plan is ready. Respond GO to begin implementation or NO-GO to revise.
```

### 5. Save the plan

Save as `docs/rpi/<feature-slug>/plan.md` with this structure:

```
FEATURE: <name>
PHASE: Implementation

## New files
1. src/docforge/libs/.../new_module.py
   - Class: NewClass(LoggerClass)
   - Protocol: implements XxxProtocol
   - Key methods: ...

## Modified files
1. src/docforge/libs/pipeline/engine.py
   - Add DAG node: ...
   - Wire dependency: ...

## Migration
- migrations/versions/00N_<name>.py
  - Table/column: ...

## Env vars
- NEW_FLAG=false  # disable by default

## Test strategy
- Unit: test_new_module.py — mock provider, assert output
- Integration: run pipeline with S_ENABLED=true
```
