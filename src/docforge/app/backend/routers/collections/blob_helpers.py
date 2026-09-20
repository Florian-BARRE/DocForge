# ====== Code Summary ======
# CollectionBlobHelpers — the pure (store-free) pipeline-BLOB logic behind the collections routes,
# split out of CollectionHelpers so blob concerns own their own file. It selects the stock blob for
# a creation preset and canonicalizes a posted blob (heal → validate → stamp). The reindex decision
# now lives in the DERIVED signature (shared_libs.services.db.index_signature), not here.

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
from shared_libs.pipelines.search import SearchPipeline

# ====== Local Project Imports ======
from ...utils.pipeline_validation import PipelineBlobValidator


class CollectionBlobHelpers:
    """Static, store-free pipeline-blob helpers for the collections routes (preset, canonicalize)."""

    logger = loggerplusplus.bind(identifier="CollectionBlobHelpers")

    def __new__(cls, *args: object, **kwargs: object) -> None:
        raise TypeError("CollectionBlobHelpers is a static-only class and cannot be instantiated.")

    # -------------------- presets & blobs --------------------
    @staticmethod
    def preset_blob(preset: str | None) -> dict:
        """The stock ingestion blob a creation preset selects (used when no explicit pipeline is posted).

        Delegates to the pipeline facade so the curated topologies have ONE definition (the facade's
        ``preset_blob``); an unknown/omitted name falls back to the full default there.

        Args:
            preset (str | None): The ingestion preset name (e.g. ``"light"``, ``"ocr_scan"``), or None.

        Returns:
            dict: The selected stock blob as a JSON-ready dict.
        """
        return IngestPipeline.preset_blob(preset).model_dump(mode="json")

    @staticmethod
    def search_preset_blob(preset: str | None) -> dict:
        """The stock SEARCH blob a creation preset selects (stored on ``collection.search``).

        Delegates to the search facade's ``preset_blob``. Returns ``{}`` for no/default selection so
        a collection keeps using the stock hybrid default via the normal ``{}`` sentinel, and only a
        NON-default preset is persisted as an explicit search graph.

        Args:
            preset (str | None): The search preset name (e.g. ``"hybrid_rerank"``), or None.

        Returns:
            dict: The selected stock search blob as a JSON-ready dict, or ``{}`` for the default.
        """
        # 1. No selection, or the default (== the stock hybrid default_blob) → the {} sentinel, so
        #    the stored contract is byte-identical to an omitted search_preset (no redundant graph).
        if preset is None or preset == "hybrid":
            return {}
        return SearchPipeline.preset_blob(preset).model_dump(mode="json")

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
        # 1. Auto-heal to the current-engine topology (a stale/unrecognisable blob is a clear 422),
        #    reporting any input node the heal could not round-trip.
        try:
            canonical, dropped = BlobNormalizer.normalize_reporting(blob)
        except BlobNormalizationError as exc:
            raise HTTPException(status_code=422, detail=f"Pipeline blob cannot be migrated: {exc}")

        # 2. A graph-level edit the stage layer cannot round-trip would be SILENTLY discarded by the
        #    heal (the stored blob is reduced to its stage surface). Refuse the save loudly instead of
        #    losing the customisation without a word — the exact silent-loss this heal must not do.
        if dropped:
            raise HTTPException(
                status_code=422,
                detail=(
                    "graph-level edits are not preservable on collections — the pipeline stored on a "
                    "collection is reduced to its stage-level surface, so the graph node(s) "
                    f"{sorted(dropped)} added through the headless /edit API would be dropped on "
                    "save. Re-express the change through the stage API, or run the customised graph "
                    "headlessly instead of persisting it on the collection."
                ),
            )

        # 3. Structural validation runs on the healed, stamp-free shape (the builder forbids extras).
        PipelineBlobValidator.validate(canonical)

        # 4. Persist the stamped canonical form so future reads fast-path.
        return BlobNormalizer.stamp(canonical)


__all__ = ["CollectionBlobHelpers"]
