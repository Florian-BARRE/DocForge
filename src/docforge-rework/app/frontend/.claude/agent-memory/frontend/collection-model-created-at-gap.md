---
name: collection-model-created-at-gap
description: CollectionModel (API) does not expose created_at even though the DB row has it — hand off to backend agent before adding a "created" column to the UI
metadata:
  type: project
---

The `collection` table (`shared/libs/services/db/postgresql/tables/collections/collection.py`)
inherits `TimestampedMixin`, so `created_at`/`updated_at` exist in Postgres — but
`CollectionModel` (`app/backend/routers/collections/models.py`) does not include them, so the
`/api/v1/collections` responses never carry a timestamp.

**Why:** `CollectionsPage`/`CollectionCard` were asked to show a "created" date; since the REST
contract has no such field and this frontend agent does not own the contract, the card was built
without it rather than inventing a client-side stand-in.

**How to apply:** if a "created" column/sort is wanted on the collections list, hand off to the
**backend** craftsman to add `created_at: datetime` to `CollectionModel` + `_to_model` in
`collections/router.py` first — then extend `Collection` in `src/api/collections.ts` and surface it
in `CollectionCard.tsx`.
