"""StorageFootprintFacade + StorageFootprintHelpers: the byte arithmetic, in isolation. The store
APIs (Postgres aggregates, Qdrant profile) are mocked to canned inputs — nothing hits a DB or Qdrant
— so the tests lock the FORMULAS and the ROLL-UP: dense/sparse/payload sizing, the per-document
Postgres bucket fold, S3 dedup (a shared blob counted once physically but in each doc's logical sum),
the null-document observability rows folding into the collection total, per-document sorting, and the
grand total using the deduped physical S3 cost."""

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

from shared_libs.services.db.facades import storage_footprint_facade as facade_mod
from shared_libs.services.db.facades.storage_footprint_facade import StorageFootprintFacade
from shared_libs.services.db.facades.storage_footprint_helpers import StorageFootprintHelpers
from shared_libs.services.db.qdrant import VectorNames
from shared_libs.services.db.qdrant.apis import QdrantProfile

# Two stable document ids used across the facade roll-up assertions.
DOC_A = uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
DOC_B = uuid.UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")


# --------------------------------------------------------------------------- #
# StorageFootprintHelpers — the pure formulas.
# --------------------------------------------------------------------------- #
def test_qdrant_footprint_formula() -> None:
    """sparse = points·avg·8, payload = points·avg_bytes, dense is passed pre-summed; total is the sum."""
    footprint = StorageFootprintHelpers.qdrant_footprint(
        points=10, dense_bytes=40960, avg_sparse_entries=5.0, avg_payload_bytes=200.0
    )
    assert footprint.dense_bytes == 40960
    assert footprint.sparse_bytes == 10 * 5 * 8  # 400
    assert footprint.payload_bytes == 10 * 200  # 2000
    assert footprint.total_bytes == 40960 + 400 + 2000
    assert footprint.estimated is True


def test_qdrant_footprint_truncates_fractional_estimates() -> None:
    """Fractional sample averages floor to whole bytes (int truncation), never round up."""
    footprint = StorageFootprintHelpers.qdrant_footprint(
        points=3, dense_bytes=0, avg_sparse_entries=5.5, avg_payload_bytes=10.7
    )
    assert footprint.sparse_bytes == int(3 * 5.5 * 8)  # int(132.0) == 132
    assert footprint.payload_bytes == int(3 * 10.7)  # int(32.099..) == 32


def test_dense_bytes_weights_each_vector_by_its_own_carrier_count() -> None:
    """content_dense rides every point; a meta vector only its carriers — NOT the whole collection."""
    # content on all 10 points, but the semantic meta vector only on 4 → the two are charged apart.
    dense = StorageFootprintHelpers.dense_bytes(
        points_by_vector={"content_dense": 10, "meta_topic_dense": 4},
        dense_dims={"content_dense": 1024, "meta_topic_dense": 1024},
    )
    assert dense == 10 * 1024 * 4 + 4 * 1024 * 4  # 40960 + 16384 == 57344


def test_dense_bytes_ignores_undeclared_and_missing_vectors() -> None:
    """A carrier for a vector Qdrant does not declare (reindex-pending) holds no bytes yet."""
    dense = StorageFootprintHelpers.dense_bytes(
        points_by_vector={"content_dense": 5, "meta_pending_dense": 5},
        dense_dims={"content_dense": 8},  # meta_pending_dense not declared
    )
    assert dense == 5 * 8 * 4  # only the declared content vector counts


def test_postgres_footprint_sums_buckets_with_missing_defaulting_to_zero() -> None:
    """An absent bucket contributes 0; the total is the honest sum of every bucket."""
    footprint = StorageFootprintHelpers.postgres_footprint(
        {"documents": 200, "ir_blocks": 200, "chunks": 50, "metadata": 30, "observability": 40}
    )
    assert footprint.enrichment_bytes == 0  # never supplied
    assert footprint.documents_bytes == 200
    assert footprint.total_bytes == 200 + 200 + 50 + 30 + 40  # 520
    assert footprint.estimated is True


# --------------------------------------------------------------------------- #
# StorageFootprintFacade — the roll-up over mocked store APIs.
# --------------------------------------------------------------------------- #
def _fake_postgres() -> MagicMock:
    """A postgres client whose session() is an async context manager yielding a sentinel session."""
    postgres = MagicMock()
    session_cm = MagicMock()
    session_cm.__aenter__ = AsyncMock(return_value=SimpleNamespace())
    session_cm.__aexit__ = AsyncMock(return_value=False)
    postgres.session = MagicMock(return_value=session_cm)
    return postgres


def _wire_apis(monkeypatch) -> None:
    """Patch the Postgres + Qdrant footprint APIs with canned aggregate outputs (no store touched)."""
    # 1. Two documents, each with its own S3 + Postgres + Qdrant shape.
    monkeypatch.setattr(
        facade_mod.StorageFootprintApi,
        "document_names",
        AsyncMock(return_value=[(DOC_A, "attention.pdf"), (DOC_B, "mineru.pdf")]),
    )
    # 2. Per-document Postgres bytes, including a NULL-document observability row (a job with no doc).
    monkeypatch.setattr(
        facade_mod.StorageFootprintApi,
        "per_document_pg",
        AsyncMock(
            return_value=[
                (DOC_A, "documents", 100),
                (DOC_A, "ir_blocks", 200),
                (DOC_A, "chunks", 50),
                (DOC_B, "documents", 100),
                (DOC_B, "metadata", 30),
                (None, "observability", 40),
            ]
        ),
    )
    # 3. EXACT per-document S3 bytes (logical, deduped per document).
    monkeypatch.setattr(
        facade_mod.StorageFootprintApi,
        "s3_per_document",
        AsyncMock(return_value=[(DOC_A, 1000, 500), (DOC_B, 2000, 0)]),
    )
    # 4. Physical unique < logical sum (3500): DOC_A and DOC_B share a 500-byte blob → 3000.
    monkeypatch.setattr(
        facade_mod.StorageFootprintApi,
        "s3_physical_unique",
        AsyncMock(return_value=3000),
    )
    # 5. No semantic metadata fields → only the content dense vector is charged (the demo case).
    monkeypatch.setattr(
        facade_mod.StorageFootprintApi,
        "semantic_field_carriers",
        AsyncMock(return_value=[]),
    )
    # 6. Qdrant profile: 10 points total, one 1024-dim content vector, sampled averages, facet split.
    monkeypatch.setattr(
        facade_mod.QdrantStorageApi,
        "profile",
        AsyncMock(
            return_value=QdrantProfile(
                total_points=10,
                dense_dims={"content_dense": 1024},
                avg_sparse_entries=5.0,
                avg_payload_bytes=200.0,
                per_document_points={str(DOC_A): 6, str(DOC_B): 4},
            )
        ),
    )


async def test_collection_footprint_rolls_up_all_three_stores(monkeypatch) -> None:
    """The facade composes exact S3, estimated Postgres + Qdrant into per-doc + collection totals."""
    _wire_apis(monkeypatch)
    facade = StorageFootprintFacade(_fake_postgres(), MagicMock())

    result = await facade.collection_footprint(uuid.uuid4())

    # 1. S3 collection totals: logical sum (3500) vs deduped physical (3000).
    assert result.s3.original_bytes == 3000  # 1000 + 2000
    assert result.s3.rendered_bytes == 500
    assert result.s3.total_bytes == 3500
    assert result.s3.physical_unique_bytes == 3000
    assert result.s3.estimated is False

    # 2. Postgres collection total folds every bucket INCLUDING the null-document observability row.
    assert result.postgres.observability_bytes == 40
    assert result.postgres.total_bytes == 520

    # 3. Qdrant collection total from the 10-point tally.
    assert result.qdrant.dense_bytes == 10 * 1024 * 4
    assert result.qdrant.sparse_bytes == 10 * 5 * 8
    assert result.qdrant.total_bytes == 40960 + 400 + 2000  # 43360

    # 4. Grand total uses the DEDUPED S3 cost (3000), not the logical sum (3500).
    assert result.grand_total_bytes == 3000 + 520 + 43360  # 46880


async def test_collection_footprint_per_document_breakdown_is_sorted(monkeypatch) -> None:
    """Each document's per-store bytes are correct and the list is heaviest-first (the top-N)."""
    _wire_apis(monkeypatch)
    facade = StorageFootprintFacade(_fake_postgres(), MagicMock())

    documents = (await facade.collection_footprint(uuid.uuid4())).documents

    # 1. DOC_A dominates (its 6 Qdrant points outweigh DOC_B's larger S3) → sorted first.
    assert [doc.document_id for doc in documents] == [DOC_A, DOC_B]

    # 2. DOC_A: S3 1500 (logical == physical at doc level) + PG 350 + Qdrant(6 pts) 26016.
    doc_a = documents[0]
    assert doc_a.s3.total_bytes == 1500
    assert doc_a.s3.physical_unique_bytes == 1500
    assert doc_a.postgres.total_bytes == 350  # 100 + 200 + 50
    assert doc_a.qdrant.points == 6
    assert doc_a.qdrant.total_bytes == 6 * 1024 * 4 + 6 * 5 * 8 + 6 * 200  # 26016
    assert doc_a.total_bytes == 1500 + 350 + 26016

    # 3. DOC_B: S3 2000 + PG 130 + Qdrant(4 pts) 17344.
    doc_b = documents[1]
    assert doc_b.postgres.total_bytes == 130  # 100 + 30
    assert doc_b.qdrant.points == 4
    assert doc_b.total_bytes == 2000 + 130 + (4 * 1024 * 4 + 4 * 5 * 8 + 4 * 200)


async def test_collection_footprint_charges_semantic_meta_vector_only_to_its_carriers(
    monkeypatch,
) -> None:
    """A semantic field's dense vector is charged ONLY to the points of the documents that populate
    it — NOT to every point in the collection (the over-count bug this locks)."""
    _wire_apis(monkeypatch)
    # DOC_A populates semantic field 'topic'; DOC_B does not. Its meta dense vector is declared.
    meta_vector = VectorNames.field_dense("topic")
    assert meta_vector == "meta_topic_dense"
    monkeypatch.setattr(
        facade_mod.StorageFootprintApi,
        "semantic_field_carriers",
        AsyncMock(return_value=[(DOC_A, "topic")]),
    )
    monkeypatch.setattr(
        facade_mod.QdrantStorageApi,
        "profile",
        AsyncMock(
            return_value=QdrantProfile(
                total_points=10,
                dense_dims={"content_dense": 1024, meta_vector: 1024},
                avg_sparse_entries=5.0,
                avg_payload_bytes=200.0,
                per_document_points={str(DOC_A): 6, str(DOC_B): 4},
            )
        ),
    )
    facade = StorageFootprintFacade(_fake_postgres(), MagicMock())

    result = await facade.collection_footprint(uuid.uuid4())
    by_id = {doc.document_id: doc for doc in result.documents}

    # 1. Collection dense = content on all 10 points + meta_topic on only DOC_A's 6 carrier points.
    assert result.qdrant.dense_bytes == 10 * 1024 * 4 + 6 * 1024 * 4  # 40960 + 24576 == 65536
    # 2. NOT the buggy "every point carries every declared vector" figure (10 · 2048 · 4 = 81920).
    assert result.qdrant.dense_bytes != 10 * 2048 * 4

    # 3. DOC_A carries content + meta on its 6 points; DOC_B carries content only on its 4.
    assert by_id[DOC_A].qdrant.dense_bytes == 6 * 1024 * 4 + 6 * 1024 * 4  # 49152
    assert by_id[DOC_B].qdrant.dense_bytes == 4 * 1024 * 4  # 16384


async def test_collection_footprint_reports_zero_qdrant_when_never_embedded(monkeypatch) -> None:
    """A collection with no Qdrant space (profile None) reports zero vectors, never an error."""
    _wire_apis(monkeypatch)
    monkeypatch.setattr(facade_mod.QdrantStorageApi, "profile", AsyncMock(return_value=None))
    facade = StorageFootprintFacade(_fake_postgres(), MagicMock())

    result = await facade.collection_footprint(uuid.uuid4())

    # 1. No vectors anywhere — Qdrant contributes zero to the collection and every document.
    assert result.qdrant.points == 0
    assert result.qdrant.total_bytes == 0
    assert all(doc.qdrant.total_bytes == 0 for doc in result.documents)
    # 2. S3 + Postgres are unaffected; the grand total is just those two.
    assert result.grand_total_bytes == 3000 + 520
