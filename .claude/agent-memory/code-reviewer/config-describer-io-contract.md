---
name: config-describer-io-contract
description: The recursive config_describer must perform ZERO network I/O; only the flat describe.py surface probes provider availability
metadata:
  type: project
---

The recursive `config_describer.py` (common_libs/pipeline/assembly) is a config-FORM
describer and is I/O-FREE BY CONTRACT.

**Why:** GET /discovery once took ~45 s because the recursive walk re-described the embed
providers ~3× (embed.chain + embed.sparse + semantic.embed) and each provider's
`availability()` hook does a blocking ~1 s socket probe; plus `auto_import` (a
`pkgutil.walk_packages` filesystem scan) was being re-run per provider-union node.

**How to apply:** when reviewing this file (or any config-FORM describe path):
- Confirm NO call to `availability()` / socket / httpx / connect in the describe path —
  references to "availability" must be in comments/docstrings only. Choices report
  `available=True` unconditionally; UP/DOWN is a /monitoring/resources concern.
- Confirm `auto_import` runs ONCE per process: guarded by the process-global
  `_registered` boolean in `_ensure_registered()`. The recursive class `describe()` re-calls
  `_ensure_registered()` but that is the cheap early-return; the filesystem walk
  (`_auto_import_all`) is NOT re-entered.
- Confirm the per-build `_describe_cache` is reset ONLY in the module-level `describe()`
  entry point (the true public API), NOT in the class method (which re-enters per provider).
- The flat sibling `describe.py` / `DescribeSurface._auto_providers` DOES probe
  `availability(cfg)` — that is intentional and separate; do not "fix" it to match.

Test guard: `tests/units/test_config_describer.py` asserts the tree shape (gates, enums,
nested embed union under semantic, secret masking) but deliberately does NOT assert probed
availability — keep it that way.
