---
name: gen-types-constraint
description: npm run gen:types requires a running backend at OPENAPI_URL — use overlay intersections in types.ts for new backend fields
metadata:
  type: feedback
---

`npm run gen:types` hits the live OpenAPI schema from a running backend container.
It cannot run in a static/offline context.

**Rule:** Never hand-edit `generated.ts`. When the backend adds new fields to Pydantic models:
1. Add overlay intersections in `api/types.ts` (e.g., `Schemas['ConfigMetaField'] & { origin?: ... }`)
2. Comment the overlay with "Added server-side after last gen:types run"
3. Once the backend is deployed and reachable, run `npm run gen:types` and remove the overlay

**Why:** Editing generated.ts breaks on the next regeneration. Overlays survive regeneration — they narrow/extend the generated type safely.

**How to apply:** Any time a task requires new backend fields that are not yet in generated.ts, add them as overlay intersections in types.ts. Never touch generated.ts.
