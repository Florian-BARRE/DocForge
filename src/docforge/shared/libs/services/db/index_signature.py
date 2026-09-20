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
from .postgresql.tables import MetadataField

# The embed-node config keys that define the vector space (a change to any means already-stored
# vectors were produced by a different/incompatible embedder → the collection must be reindexed).
_EMBED_VECTOR_KEYS = ("base_url", "model", "embed_sparse", "embed_semantic_fields")


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
        """A stable fingerprint of every embed node's vector-space-affecting config in a pipeline blob.

        Two blobs with the same fingerprint produce vectors in the same space; a difference means a
        reindex is required (e.g. a swapped embed model/provider, toggled sparse). Walks nested
        ForEach/group bodies so an embed node anywhere in the graph is captured.

        Args:
            blob (dict): The collection's stored ingestion pipeline blob.

        Returns:
            list: The sorted list of per-embed-node vector-space fingerprints.
        """
        fingerprint: list = []

        def walk(nodes: list) -> None:
            # 1. Record every embed node's vector-space config, then recurse into any nested body.
            for node in nodes:
                if node.get("family") == "embed":
                    config = node.get("config") or {}
                    fingerprint.append(
                        (
                            node.get("id"),
                            node.get("kind"),
                            tuple((key, config.get(key)) for key in _EMBED_VECTOR_KEYS),
                        )
                    )
                body = node.get("body")
                if isinstance(body, dict):
                    walk(body.get("nodes") or [])

        walk(blob.get("nodes") or [])
        return sorted(fingerprint)

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
        # 1. The two reindex-relevant surfaces (metadata vectors + embed space); filterable excluded.
        payload = {
            "meta": cls._metadata_surface(schema_rows),
            "embed": cls.embed_vector_space(pipeline_blob or {}),
        }
        # 2. Canonical JSON (sorted keys, stable tuple order) → a deterministic digest.
        canonical = json.dumps(payload, sort_keys=True, default=str)
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def collection_index_signature(pipeline_blob: dict, schema_rows: Sequence[MetadataField]) -> str:
    """Module-level wrapper over ``CollectionIndexSignature.compute`` (the DESIGN's exact name)."""
    return CollectionIndexSignature.compute(pipeline_blob, schema_rows)


__all__ = ["CollectionIndexSignature", "collection_index_signature"]
