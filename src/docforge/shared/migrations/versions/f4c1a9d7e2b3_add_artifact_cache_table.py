# ====== Code Summary ======
# create the `artifact_cache` table + widen `blob.kind` for the new STAGE_ARTIFACT value
#
# Revision: f4c1a9d7e2b3
# Revises: c9a4e1b7f302
# Created: 2026-09-02 00:00:00.000000
#
# Phase 5 (P0) — per-stage artifact cache storage. Two coupled changes:
#
# 1. New table ``artifact_cache``: one row per cached stage output. The cached BYTES live in S3
#    (registered in ``blob`` under their content_hash); this table is the pointer + GC bookkeeping.
#    Mirrors the ORM model exactly (shared_libs...tables/blobs/artifact_cache.py) — env.py runs
#    compare_type=True, so any width/nullability drift surfaces on the next --autogenerate.
#
# 2. Widen ``blob.kind`` VARCHAR(13) -> VARCHAR(14). ``BlobKind`` is a value_enum
#    (Enum(native_enum=False)) with NO explicit length, so its VARCHAR width is derived from the
#    LONGEST member value. The new member ``STAGE_ARTIFACT = "stage_artifact"`` is 14 chars, one more
#    than the previous longest ("canonical_pdf" = 13). Adding the member is a code constant, but the
#    column width is NOT code-only: without this ALTER, inserting kind='stage_artifact' would raise
#    "value too long for type character varying(13)". value_enum sets native_enum=False with the
#    default create_constraint=False, so there is NO CHECK constraint and NO Postgres ENUM type to
#    alter — the widening is a pure VARCHAR length change.
#
# Key design choices for artifact_cache:
# - PK is the natural ``cache_key`` (sha256 hex Merkle key), NOT a surrogate: the only lookup is by
#   exact key, so the natural key IS the identity.
# - NO foreign key on ``document_id`` or ``collection_id``. The cache row must never block (nor be
#   required to survive) a document/collection delete; the ids are stored raw for attribution and GC
#   scoping, and GC reclaims orphaned rows + their S3 bytes on its own schedule. Same precedent as
#   ``audit_log`` / ``idempotency_key`` (actor ids stored raw, no referential coupling). collection_id
#   is NOT NULL, so ON DELETE SET NULL is not even an option here — no-FK is the only consistent choice.
# - Three GC read-path btree indexes: (collection_id, last_hit_at) for the LRU/TTL sweep + per-
#   collection cap; (content_hash) for the ref-count orphan sweep; (document_id) for on-doc-delete
#   cleanup. None overlaps the PK (exact-key lookup only).
# - ``hit_count`` carries server_default 0 so a bare INSERT-on-store needs no explicit count.
#
# Data safety:
# - UPGRADE is additive and non-destructive: it only CREATEs a brand-new table and WIDENs a VARCHAR
#   (widening never rewrites/loses data). No existing row is touched.
# - DOWNGRADE drops ``artifact_cache`` (discarding accumulated cache pointers — expected for a cache
#   table; the S3 bytes themselves are left for GC) and NARROWS blob.kind back to VARCHAR(13). The
#   narrowing is SAFE-BY-FAILURE: Postgres validates every value fits and RAISES (does not truncate)
#   if any ``blob`` row still carries kind='stage_artifact'. A real downgrade must therefore first
#   reclassify/delete those stage-artifact blobs. This loud, non-destructive failure is intentional —
#   it prevents silent data loss.

# ====== Third-Party Library Imports ======
import sqlalchemy as sa
from alembic import op

# Revision identifiers used by Alembic.
revision = "f4c1a9d7e2b3"
down_revision = "c9a4e1b7f302"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Widen blob.kind for STAGE_ARTIFACT, then create the artifact_cache table and its GC indexes."""
    # 1. Widen blob.kind VARCHAR(13) -> VARCHAR(14) so the new "stage_artifact" (14 chars) value fits.
    #    Widening a varchar never rewrites rows or loses data.
    op.alter_column(
        "blob",
        "kind",
        existing_type=sa.String(length=13),
        type_=sa.String(length=14),
        existing_nullable=False,
    )

    # 2. The artifact_cache table: natural sha256 PK, S3 pointer, debug/audit provenance, raw
    #    attribution ids (no FK), size accounting, and hit recency/popularity. Constraint name follows
    #    the schema's NAMING_CONVENTION (pk_artifact_cache).
    op.create_table(
        "artifact_cache",
        sa.Column("cache_key", sa.String(length=64), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("stage_key", sa.Text(), nullable=False),
        sa.Column(
            "artifact_type",
            sa.Enum("parse_ir", name="artifacttype", native_enum=False),
            nullable=False,
        ),
        sa.Column("engine_version", sa.String(length=128), nullable=False),
        sa.Column("document_id", sa.Uuid(), nullable=True),
        sa.Column("collection_id", sa.Uuid(), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("last_hit_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("hit_count", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.PrimaryKeyConstraint("cache_key", name=op.f("pk_artifact_cache")),
    )

    # 3. GC read-path indexes.
    op.create_index(
        "ix_artifact_cache_collection_last_hit",
        "artifact_cache",
        ["collection_id", "last_hit_at"],
        unique=False,
    )
    op.create_index(
        "ix_artifact_cache_content_hash", "artifact_cache", ["content_hash"], unique=False
    )
    op.create_index(
        "ix_artifact_cache_document_id", "artifact_cache", ["document_id"], unique=False
    )


def downgrade() -> None:
    """Drop artifact_cache, then narrow blob.kind back to VARCHAR(13) (fails loudly on live rows)."""
    # 1. Drop the cache indexes then the table (discards cache pointers; S3 bytes left for GC).
    op.drop_index("ix_artifact_cache_document_id", table_name="artifact_cache")
    op.drop_index("ix_artifact_cache_content_hash", table_name="artifact_cache")
    op.drop_index("ix_artifact_cache_collection_last_hit", table_name="artifact_cache")
    op.drop_table("artifact_cache")

    # 2. Narrow blob.kind back to VARCHAR(13). Postgres RAISES (never truncates) if any row still
    #    carries kind='stage_artifact' — clean up those blobs before downgrading. Safe by failure.
    op.alter_column(
        "blob",
        "kind",
        existing_type=sa.String(length=14),
        type_=sa.String(length=13),
        existing_nullable=False,
    )
