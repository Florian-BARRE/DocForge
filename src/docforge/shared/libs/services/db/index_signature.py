# ====== Code Summary ======
# CollectionIndexSignature — the ONE deterministic fingerprint of a collection's REINDEX-RELEVANT
# config: the vector-affecting metadata surface (semantic/lexical fields — ``filterable`` is EXCLUDED
# because its Qdrant payload index is added LIVE by reconcile_store, needing no reindex) plus the
# embed vector-space fingerprint (a swapped embed model/provider/sparse produces incompatible
# vectors). Shared so the app (deriving ``needs_reindex`` at every config write) and the worker
# (advancing the indexed baseline at the ingestion edge) hash the SAME definition — the flag is
# DERIVED against an indexed baseline, never a sticky one-way boolean.

# ====== Standard Library Imports ======
import hashlib
import json
from collections.abc import Sequence

# ====== Third-Party Library Imports ======
from loggerplusplus import loggerplusplus

# ====== Internal Project Imports ======
from .index_embed_baseline import EmbedBaseline
from .index_signature_embed import EmbedVectorSpace
from .postgresql.tables import MetadataField


class CollectionIndexSignature:
    """Static hasher of a collection's reindex-relevant config (metadata surface + embed space)."""

    logger = loggerplusplus.bind(identifier="CollectionIndexSignature")

    def __new__(cls, *args: object, **kwargs: object) -> None:
        raise TypeError(
            "CollectionIndexSignature is a static-only class and cannot be instantiated."
        )

    @staticmethod
    def _metadata_surface(schema_rows: Sequence[MetadataField]) -> list:
        """The sorted vector-affecting metadata surface — one tuple per semantic/lexical field.

        A ``(field_name, field_type, semantic, lexical)`` tuple for every row that is semantic OR
        lexical. ``filterable`` is DELIBERATELY excluded: a filterable-only payload index is added
        LIVE by ``reconcile_store`` (no reindex), so a filterable-only toggle must never move the
        signature — the exact over-flagging the old sticky boolean got wrong.

        Args:
            schema_rows (Sequence[MetadataField]): The collection's metadata schema rows.

        Returns:
            list: The sorted list of vector-affecting field tuples.
        """
        surface = [
            (
                row.field_name,
                str(getattr(row.field_type, "value", row.field_type)),
                bool(row.semantic),
                bool(row.lexical),
            )
            for row in schema_rows
            if row.semantic or row.lexical
        ]
        return sorted(surface)

    @staticmethod
    def embed_vector_space(blob: dict) -> list:
        """The CANONICAL fingerprint of every embed node's vector space (see EmbedVectorSpace).

        A legacy single-provider embed node and its migrated dense_sparse form fingerprint the same;
        a swapped provider/model/endpoint on either slot, or an axis switched on/off, differs.

        Args:
            blob (dict): The collection's stored ingestion pipeline blob.

        Returns:
            list: The sorted per-embed-node fingerprints.
        """
        return EmbedVectorSpace.canonical(blob or {})

    @staticmethod
    def __digest(meta: list, embed: list) -> str:
        """sha256 of the canonical JSON of (metadata surface, embed space)."""
        canonical = json.dumps({"meta": meta, "embed": embed}, sort_keys=True, default=str)
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    @classmethod
    def compute(cls, pipeline_blob: dict, schema_rows: Sequence[MetadataField]) -> str:
        """Deterministically hash a collection's reindex-relevant config into a stable signature.

        Args:
            pipeline_blob (dict): The collection's stored ingestion pipeline blob.
            schema_rows (Sequence[MetadataField]): The collection's metadata schema rows.

        Returns:
            str: A hex sha256 over the (metadata surface, embed vector space) — identical for two
            configs that would index into the same vector space, different otherwise. A filterable-only
            change leaves it unchanged; a semantic/lexical/type or embed change moves it.
        """
        # The two reindex-relevant surfaces (metadata vectors + embed space); filterable excluded.
        return cls.__digest(
            cls._metadata_surface(schema_rows), cls.embed_vector_space(pipeline_blob or {})
        )

    @classmethod
    def embed_signature(cls, pipeline_blob: dict) -> str:
        """The PER-AXIS embed-only baseline of a pipeline blob (the content-vector baseline).

        Args:
            pipeline_blob (dict): The collection's stored ingestion pipeline blob.

        Returns:
            str: ``<dense digest>:<sparse digest>`` (see EmbedBaseline) — unchanged by any
                metadata-schema edit, and comparable per axis by the rebuild.
        """
        return EmbedBaseline.signature(pipeline_blob or {})

    @classmethod
    def candidates(cls, pipeline_blob: dict, schema_rows: Sequence[MetadataField]) -> set[str]:
        """Every signature equivalent to the current config: the canonical one + legacy spellings.

        A collection indexed BEFORE the dense/sparse slots holds a baseline hashed over the legacy
        embed fingerprint; its blob healed to the slot node hashes differently although the vectors
        are the same. Comparing against the legacy-equivalent signatures too keeps it current.

        Args:
            pipeline_blob (dict): The collection's stored ingestion pipeline blob.
            schema_rows (Sequence[MetadataField]): The collection's metadata schema rows.

        Returns:
            set[str]: The canonical signature plus every legacy-equivalent one.
        """
        meta = cls._metadata_surface(schema_rows)
        legacy = EmbedVectorSpace.legacy_equivalents(pipeline_blob or {})
        return {cls.compute(pipeline_blob, schema_rows)} | {cls.__digest(meta, e) for e in legacy}

    @classmethod
    def embed_candidates(cls, pipeline_blob: dict) -> set[str]:
        """The embed-only counterpart of ``candidates``: the per-axis signature + whole-space ones."""
        return EmbedBaseline.candidates(pipeline_blob or {})


def collection_index_signature(pipeline_blob: dict, schema_rows: Sequence[MetadataField]) -> str:
    """Module-level wrapper over ``CollectionIndexSignature.compute`` (the DESIGN's exact name)."""
    return CollectionIndexSignature.compute(pipeline_blob, schema_rows)


__all__ = ["CollectionIndexSignature", "collection_index_signature"]
