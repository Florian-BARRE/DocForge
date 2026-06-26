# Design — Simplified auth: single root + permissioned API keys

> Status: FOR BUILD. Replaces the multi-user / collaborators / impersonation system (UI-5,
> commits 772c2dc + e9bc772) with a much simpler model the user asked for: one root account that
> creates API keys, each key scoped per-collection with read/write/admin shortcuts + optional
> fine-grained endpoint groups.

## Model
- **Login**: ONLY the `root` account (bootstrapped from env: AUTH_ROOT_USERNAME/PASSWORD; password → JWT = full access). No other login accounts. The UI is root-only.
- **API keys** (created by root, owned by root): the SOLE delegated-access mechanism (for MCP/scripts/integrations). Each key carries a **permissions** scope.
- **Permissions scope** (stored on the api_key row, JSONB `permissions`):
  ```
  { "entries": [
      { "collection_id": "*" | "<uuid>",
        "role": "read" | "write" | "admin" | "custom",   # the shortcut chosen (display)
        "capabilities": ["documents.read", "search", ...] # effective allowed set
      } ] }
  ```
  - `collection_id: "*"` = applies to ALL collections (incl. future ones).
  - `role` is a shortcut that EXPANDS to a capability set; `"custom"` = hand-picked capabilities.

## Capability taxonomy (per collection — "assez fin")
- `documents.read` — list/get documents, files (original/pdf/markdown), pages, chunks(read), jobs(read)
- `documents.write` — ingest, update metadata, reingest, delete documents
- `search` — run search
- `config.read` — config state/schema/history
- `config.write` — config update/rollback
- `chunks.write` — edit chunk text
- `collection.admin` — delete collection, manage limits

**Shortcuts** (UI chips):
- **read**  = {documents.read, search, config.read}
- **write** = read ∪ {documents.write, config.write, chunks.write}
- **admin** = write ∪ {collection.admin}

Global non-collection routes (health, discovery, monitoring, jobs-list) = allowed for any valid key (read-ish) or tag them `monitoring.read` if we want to gate them; default: allow.

## Enforcement
- Each collection-scoped route is tagged with its capability (replace `require_collection_role(READ|WRITE|ADMIN)` with `require_capability("documents.read" | ...)`). The dep resolves the principal + the collection_id from the path and checks the capability.
- Principal resolution:
  - root password-JWT  → full access (all caps, all collections).
  - the static root env API key (AUTH_ROOT_API_KEY) → full access.
  - a created API key → allow iff its `permissions` grant the route's capability on the path's collection (an entry with collection_id matching OR "*", whose capabilities include the route cap).
- 403 with a precise message when the key lacks the capability (verbose-error convention).

## Removed (the pivot)
- `users` router (CRUD) + multi-user management. (root stays, env-bootstrapped.)
- `access`/collaborators router + the `collection_grant` table + grant logic.
- impersonation endpoint + the Principal `impersonated_by` machinery.
- Frontend: Users panel, Collaborators/Access tab, impersonation banner/actAs, the per-user panel.

## Migration
- ADD `api_key.permissions` JSONB (nullable; null/legacy key ⇒ treat as full access for backward-compat, OR backfill the existing root key to full). 
- DROP `collection_grant` table. Keep `app_user` (holds root; api_key.user_id → root). DROP impersonation has no table. (migration-engineer authors it.)

## Frontend (one simple page)
- root login → a single **"API Keys"** view: list (name, scope summary e.g. "all: admin" or "collA: write, collB: read", created, last used, revoked) + **Create key** (name + a permission builder: pick "all collections" or specific collections, set read/write/admin per scope via chips, an "Advanced" toggle to fine-pick capability groups) + revoke (+ plaintext-once reveal). No Users, no Collaborators, no impersonation.

## Build order
AUTH-A backend (permissions model + capability route tags + enforcement + migration + remove users/access/impersonation + tests) → AUTH-B frontend (the single API Keys page + remove users/collaborators/impersonation UI).
