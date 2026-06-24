# ====== Code Summary ======
# DocumentStaleness — decides whether an ingested document is out of date with respect to
# the collection's CURRENT config, by comparing the actual config it was processed with
# (its pipeline_version snapshot) against the current config via ConfigRepoHelpers.reindex_diff.
#
# This is precise (and reversible): a config change that is later reverted leaves the document
# fresh, unlike a raw pipeline_version-number comparison which only ever increases.

# ====== Standard Library Imports ======
from __future__ import annotations

from typing import Any

# ====== Internal Project Imports ======
from common_libs.storage.postgres.repositories.config_repo_helpers import ConfigRepoHelpers


class DocumentStaleness:
    """
    Static helper computing per-document staleness against the current collection config.

    A document is stale when the indexing-relevant config it was processed with differs from
    the collection's current config (embedding model, indexing pipeline, or searchable schema —
    see ConfigRepoHelpers.reindex_diff). Search-config and non-searchable metadata changes never
    make a document stale.
    """

    def __new__(cls, *args: object, **kwargs: object) -> None:  # type: ignore[misc]
        raise TypeError("DocumentStaleness is a static-only class and cannot be instantiated.")

    @staticmethod
    def index_versions(versions: list[Any]) -> dict[str, dict[str, Any]]:
        """
        Build a ``pipeline_version → config`` map from config-history rows (newest-first).

        Multiple snapshots can share a pipeline_version (non-reindex changes keep the same
        tag); they share the same indexing-relevant config, so the latest one is kept.

        Args:
            versions (list): ConfigVersionModel rows ordered newest-first.

        Returns:
            dict[str, dict]: pipeline_version tag → stored config document.
        """
        index: dict[str, dict[str, Any]] = {}
        for v in versions:
            index.setdefault(v.pipeline_version, v.config)
        return index

    @staticmethod
    def evaluate(
        collection: Any,
        doc_pipeline_version: str | None,
        version_index: dict[str, dict[str, Any]],
    ) -> tuple[bool, list[str]]:
        """
        Decide whether a document is stale and explain exactly why.

        Args:
            collection (Any): The collection ORM object (current config).
            doc_pipeline_version (str | None): The pipeline_version the document was ingested with.
            version_index (dict): Output of :meth:`index_versions`.

        Returns:
            tuple[bool, list[str]]: ``(stale, reasons)``. Empty reasons when fresh.
        """
        # 1. Fast path — same version tag as the collection: definitely fresh.
        if doc_pipeline_version and doc_pipeline_version == collection.pipeline_version:
            return (False, [])

        # 2. Locate the config the document was processed with.
        snapshot = version_index.get(doc_pipeline_version or "")
        if snapshot is None:
            # No snapshot to diff against (e.g. pre-history doc): be conservative.
            return (True, ["Traité avec une configuration antérieure (snapshot indisponible)"])

        # 3. Precise diff: only index-invalidating differences make the doc stale.
        return ConfigRepoHelpers.reindex_diff(
            old_embedding_model=snapshot.get("embedding_model", ""),
            new_embedding_model=collection.embedding_model,
            old_pipeline=snapshot.get("pipeline") or {},
            new_pipeline=collection.pipeline or {},
            old_fields=snapshot.get("metadata_fields") or [],
            new_fields=list(collection.metadata_fields),
        )
