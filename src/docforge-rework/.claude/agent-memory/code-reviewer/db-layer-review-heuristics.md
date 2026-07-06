---
name: db-layer-review-heuristics
description: DB-layer (SQLAlchemy 2 async / Postgres / Qdrant) review pitfalls specific to the docforge-rework FK-only store — self-FK insert batching, unindexed FKs, enum value binding, Qdrant filter/slug gaps
metadata:
  type: feedback
---

Recurring correctness pitfalls to check on any `shared/libs/services/db/**` change in docforge-rework (FK-only, NO ORM relationship(), value_enum everywhere). Verified empirically 2026-07-03 (SQLAlchemy 2.0.51, qdrant-client 1.18.0).

**Why:** the layer is FK-only with no `relationship()`, so several safety nets the ORM normally provides are absent, and the failures are latent (scale/data-dependent), not caught by import/ruff/compile.

**How to apply:**
- **Self-referential FK inserts** (`chunk.parent_id`, `block.parent_id`): with no `relationship()`, SQLAlchemy does NOT topologically sort same-table rows — it inserts in add-order. It only "works" because RETURNING (from a server_default column like TimestampedMixin) triggers `insertmanyvalues` = ONE multi-row INSERT, and Postgres checks immediate self-FKs at end-of-statement. Past `insertmanyvalues_page_size` (default **1000**) it splits into multiple statements → a forward self-reference crossing a page boundary violates the FK. Fix = make the self-FK `deferrable=True, initially="DEFERRED"`. Flag any persist_* that batches self-referential rows without deferrable FKs.
- **Unindexed FK columns**: an FK column with `ondelete` but no leading-column btree → seq scan on every parent delete + slow access path. A `ForeignKey` does NOT create an index in Postgres; only a covering Index/PK/UniqueConstraint (leading column) counts. Composite unique constraints only cover their LEADING column. Grep each new FK for `index=True` or a covering composite.
- **Enum columns MUST use `tables/base.py value_enum`** (native_enum=False, values_callable → persists VALUES). Verified: binds `FieldOrigin.GENERATED` → `'generated'` through both the ORM add path and the raw `pg_insert` path. CHECK constraints written against values (`origin = 'user'`) match. A plain `Enum(SomeStrEnum)` would persist NAMES and silently break comparisons/checks.
- **Raw pg_insert / manual-dict paths bypass python-side `default=`**: reading `v.origin` off a transient ORM instance that never set origin returns `None` (the column default only fires on the ORM add path) → NOT NULL violation. Manual-row builders must set every non-nullable column explicitly.
- **Qdrant filter model gaps**: `filters.Range` is float-only and `search_api` emits `models.Range`, which REJECTS datetime — so `PayloadType.DATETIME` fields cannot be range-filtered despite getting a DATETIME payload index. Needs `models.DatetimeRange`.
- **VectorNames.slug collisions**: `slug()` strips accents + non-ascii, so "Café"/"Cafe", "a.b"/"a-b"/"a b" collapse to one vector name, and all-non-ascii → `meta__dense`. Nothing guards; two fields silently share one named vector. Validate slug uniqueness fail-fast at collection creation.
- **JobApi/CollectionApi `update(x=None)` = "leave unchanged"** → cannot reset a nullable column to NULL (clear job.error / release worker_id on retry). Use an `_UNSET` sentinel or dedicated lifecycle methods. (CollectionApi is unaffected — all its patch fields are non-nullable.)
