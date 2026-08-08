# ====== Code Summary ======
# CollectionBlobHelpers — the pure (store-free) pipeline-BLOB logic behind the collections routes,
# split out of CollectionHelpers so blob concerns own their own file. It selects the stock blob for
# a creation preset, canonicalizes a posted blob (heal → validate → stamp), and computes the embed
# vector-space fingerprint used to decide whether a config change forces a reindex.

# ====== Standard Library Imports ======

# ====== Third-Party Library Imports ======
from fastapi import HTTPException
from loggerplusplus import loggerplusplus

# ====== Internal Project Imports ======
from shared_libs.pipelines.ingest import (
    BlobNormalizationError,
    BlobNormalizer,
    IngestPipeline,
)

# ====== Local Project Imports ======
from ...utils.pipeline_validation import PipelineBlobValidator

# The embed-node config keys that define the vector space (a change to any means already-stored
# vectors were produced by a different/incompatible embedder → the collection must be reindexed).
_EMBED_VECTOR_KEYS = ("base_url", "model", "embed_sparse", "embed_semantic_fields")


class CollectionBlobHelpers:
    """Static, store-free pipeline-blob helpers for the collections routes (preset, canonicalize, reindex)."""

    logger = loggerplusplus.bind(identifier="CollectionBlobHelpers")

    def __new__(cls, *args: object, **kwargs: object) -> None:
        raise TypeError("CollectionBlobHelpers is a static-only class and cannot be instantiated.")

    # -------------------- protected --------------------
    @staticmethod
    def _embed_vector_space(blob: dict) -> list:
        """A stable fingerprint of every embed node's vector-space-affecting config in a pipeline blob.

        Two blobs with the same fingerprint produce vectors in the same space; a difference means a
        reindex is required (e.g. a swapped embed model/provider, toggled sparse).
        """
        fingerprint: list = []

        def walk(nodes: list) -> None:
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

    # -------------------- presets & blobs --------------------
    @staticmethod
    def preset_blob(preset: str | None) -> dict:
        """The stock ingestion blob a creation preset selects (used when no explicit pipeline is posted).

        Args:
            preset (str | None): ``"light"`` for the enrichment-free core, anything else the full default.

        Returns:
            dict: The selected stock blob as a JSON-ready dict.
        """
        blob = IngestPipeline.light_blob() if preset == "light" else IngestPipeline.default_blob()
        return blob.model_dump(mode="json")

    @staticmethod
    def canonical_pipeline(blob: dict) -> dict:
        """Heal a pipeline blob to the current engine, validate it, and return its stored form.

        The stored form is normalized (auto-migrated to the current-engine topology) and version-stamped,
        so a freshly written blob is already canonical and every subsequent run/upload fast-paths. A blob
        that cannot be migrated is a 422 with the explicit recovery, mirroring the structural validator.

        Args:
            blob (dict): The caller's (or default) pipeline blob.

        Returns:
            dict: The normalized, version-stamped blob to persist.

        Raises:
            HTTPException: 422 when the blob cannot be migrated or fails structural validation.
        """
        # 1. Auto-heal to the current-engine topology (a stale/unrecognisable blob is a clear 422).
        try:
            canonical = BlobNormalizer.normalize(blob)
        except BlobNormalizationError as exc:
            raise HTTPException(status_code=422, detail=f"Pipeline blob cannot be migrated: {exc}")

        # 2. Structural validation runs on the healed, stamp-free shape (the builder forbids extras).
        PipelineBlobValidator.validate(canonical)

        # 3. Persist the stamped canonical form so future reads fast-path.
        return BlobNormalizer.stamp(canonical)

    # -------------------- embed vector space --------------------
    @classmethod
    def embed_space_changed(cls, old_blob: dict, new_blob: dict) -> bool:
        """True when two pipeline blobs embed into DIFFERENT vector spaces (a reindex is required).

        Compares a stable fingerprint of every embed node's vector-space-affecting config; a
        difference means already-stored vectors were produced by an incompatible embedder (swapped
        model/provider, toggled sparse), so new documents must not be embedded into a space
        incompatible with the stored ones.
        """
        return cls._embed_vector_space(old_blob) != cls._embed_vector_space(new_blob)


__all__ = ["CollectionBlobHelpers"]
