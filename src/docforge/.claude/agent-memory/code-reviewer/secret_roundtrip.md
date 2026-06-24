---
name: secret-roundtrip
description: How ConfigDocument.merge_patch preserves redacted secrets — validated correct, do not flag as a bug
metadata:
  type: pattern
---

`ConfigDocument.merge_patch` (`libs/config/validation/document.py`) preserves per-collection credentials across the redacted round-trip. This is VALIDATED CORRECT — do not flag it as a secret-wipe bug on future reviews.

Mechanism:
- Config responses redact secrets to `•••` (`_REDACTION_SENTINEL`); the UI echoes that back on the next save.
- `_is_redacted_secret(key, value)` returns True when `PipelineConfigHelpers.is_secret_key(key)` AND value ∈ {`•••`, `""`, `None`}.
- In merge: such a (key,value) with a real `current` value → `continue` (keep stored secret).
- Provider chains (list of dicts) merge element-wise via `_is_mergeable_dict_list` (equal-length, all-dict) so per-element secrets survive. Differing chain length → wholesale replace (new secret expected).

Covers both cases that matter: scalar top-level secret, and secret nested inside a chain-of-dicts.

**Accepted trade-off (not a bug):** a user cannot clear a secret by sending `""` — it is preserved. Documented and intended.

**How to apply:** if a reviewer or tool flags "editing a stage wipes the api_key", verify against this mechanism before reporting — it is the thing that PREVENTS that wipe.
