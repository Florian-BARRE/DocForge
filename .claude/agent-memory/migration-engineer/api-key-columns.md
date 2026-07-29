---
name: api-key-columns
description: Semantics of the api_key table's nullable timestamp columns
metadata:
  type: project
---

`api_key` table nullable-timestamp column semantics (all `timestamptz`, NULL is meaningful):
- `revoked_at` — soft revocation marker; NULL = active.
- `expires_at` — optional hard expiry; **NULL = never expires**.
- `last_used_at` — last successful authentication, written throttled best-effort; **NULL = never used**.
- `permissions` (JSONB) — per-collection per-capability scope; **NULL = full access**.

**Why:** these NULL-means-X conventions are why the expires_at/last_used_at migration
(`c7f2a9e4b1d8`) is a plain nullable add with no server_default and no backfill — existing rows get
NULL, which is exactly the correct "never expires / never used" state.

**How to apply:** when a future migration touches api_key, preserve NULL semantics; don't add a
server_default that would flip existing rows out of their intended "never" state. See
[[migration-chain-layout]] for the chain and run commands.
