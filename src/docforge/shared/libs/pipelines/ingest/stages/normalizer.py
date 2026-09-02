# ====== Code Summary ======
# BlobNormalizer — heals a stored ingestion blob to the CURRENT engine topology, losslessly. The
# durable source of truth is NOT the fully-expanded blob (it embeds engine-STRUCTURAL wiring that
# shifts when the engine evolves — e.g. making VLM scored added new terminals) but the stage-level
# PipelineState (the user's choices). Normalizing round-trips the blob through that truth:
# blob -> StateReader.read -> PipelineState -> IngestAssembler.assemble -> current-engine blob. A
# stale blob is auto-healed to the shape the current engine builds; a manual PATCH is never needed.
#
# A reserved ``_engine_version`` key stamped INSIDE the JSONB (no DB migration) records which engine
# produced a stored blob: when it already equals the current version the blob is current-shaped and
# the expensive round-trip is skipped (the stamp is simply stripped for the pure builder, which
# forbids extra keys). A blob that cannot be read back — genuinely unparseable, or from an engine so
# old its shape is unrecognisable — raises BlobNormalizationError (surfaced as 422 / job error with
# the collection named), never a silent alteration of a customised pipeline and never a cryptic 500.

# ====== Standard Library Imports ======
from collections.abc import Mapping
from typing import Any

# ====== Third-Party Library Imports ======
from loggerplusplus import loggerplusplus
from pydantic import ValidationError

# ====== Internal Project Imports ======
from shared_libs.pipelines.build.blob import (
    ActionNodeBlob,
    ForEachNodeBlob,
    GroupNodeBlob,
)
from shared_libs.pipelines.registry import NodeRegistry

# ====== Local Project Imports ======
from .assembler import IngestAssembler
from .reader import StateReader

# The engine/blob schema version. Bump it whenever a change to the assembler, reader or a stage
# builder alters the shape the engine emits for an UNCHANGED PipelineState — so already-stored blobs
# fall through the fast path and get re-healed to the new topology on their next read.
#
# v2: the intake ContentAddress node gained a ``source_probe`` slot (commit 053f98d, native HTML/MD
# parsing) and the assembler began wiring ``bindings["address"]["source_probe"]``. That change
# altered the emitted shape but the version was NOT bumped at the time, so v1-stamped blobs stored
# BEFORE it wrongly fast-pathed as "current" and validated as invalid (missing_binding on address).
# Bumping to 2 forces every v1 blob back through the heal round-trip, re-emitting the source_probe
# wiring; blobs already carrying it round-trip identically (no drift).
ENGINE_BLOB_VERSION = 2


class BlobNormalizationError(Exception):
    """A stored blob cannot be migrated to the current engine (unparseable or too old)."""


class BlobNormalizer:
    """
    Static normalizer that heals a stored ingestion blob to the current engine's topology.

    The round-trip ``read → assemble`` is IDENTITY for every user-customisable shape (proven by the
    round-trip tests): a customised pipeline is re-emitted verbatim, a stale one is healed to the
    shape the current engine builds. A blob that cannot be read back raises BlobNormalizationError
    rather than being silently altered — silent alteration of a customised pipeline is exactly the
    class of bug this layer eliminates.
    """

    STAMP_KEY = "_engine_version"
    logger = loggerplusplus.bind(identifier="BlobNormalizer")

    def __new__(cls, *args: object, **kwargs: object) -> None:
        raise TypeError("BlobNormalizer is a static-only class and cannot be instantiated.")

    @classmethod
    def normalize(cls, blob: Mapping[str, Any]) -> dict[str, Any]:
        """
        Heal a stored blob to the current-engine topology (the version stamp stripped off).

        The returned dict is a clean graph blob ready for the pure builder (which forbids the
        reserved stamp key). It is byte-identical to the stored blob when that blob was produced by
        the current engine (fast path), otherwise the current engine's re-assembly of the same
        stage-level state.

        Args:
            blob (Mapping): The stored pipeline blob (possibly carrying a version stamp).

        Returns:
            dict: The current-engine blob, without the reserved version stamp.

        Raises:
            BlobNormalizationError: The blob cannot be read back into a PipelineState.
        """
        # 1. Fast path — a blob stamped with the current version is already current-shaped: strip
        #    the reserved key (the pure builder forbids extras) and hand it back untouched.
        clean = {key: value for key, value in blob.items() if key != cls.STAMP_KEY}
        if blob.get(cls.STAMP_KEY) == ENGINE_BLOB_VERSION:
            return clean

        # 2. Heal — round-trip through the stage-level truth to the current engine's topology.
        return cls.__heal(clean)

    @classmethod
    def stamp(cls, blob: Mapping[str, Any]) -> dict[str, Any]:
        """
        The canonical STORED form of a blob — normalized, then version-stamped.

        Storing this makes every subsequent read fast-path (the stamp matches the current version),
        and validates the blob through the same machinery a run uses.

        Args:
            blob (Mapping): The blob to canonicalise for storage.

        Returns:
            dict: The healed blob plus the reserved ``_engine_version`` stamp.

        Raises:
            BlobNormalizationError: The blob cannot be read back into a PipelineState.
        """
        return {**cls.normalize(blob), cls.STAMP_KEY: ENGINE_BLOB_VERSION}

    @classmethod
    def __heal(cls, clean: dict[str, Any]) -> dict[str, Any]:
        """Round-trip a stamp-free blob through PipelineState back to the current topology."""
        try:
            group_blob = GroupNodeBlob.model_validate(clean)
            # Detect a node whose (family, kind) the current engine no longer knows BEFORE the
            # reader runs — the reader tolerates unknown nodes and would SILENTLY drop them, healing
            # to a different pipeline. A removed kind genuinely cannot be migrated: fail loud + named.
            cls.__assert_kinds_registered(group_blob)
            state = StateReader.read(group_blob)
            healed = IngestAssembler.assemble(state)
        except (ValidationError, ValueError, KeyError, TypeError, AttributeError) as exc:
            cls.logger.error(
                f"Stored pipeline blob cannot be migrated to the current engine: {exc}"
            )
            raise BlobNormalizationError(
                "stored ingestion pipeline could not be migrated to the current engine "
                "(malformed, or it references something the current engine no longer knows) — "
                f"re-save it from the pipeline default to repair (cause: {exc})"
            ) from exc
        return healed.model_dump(mode="json")

    @classmethod
    def __assert_kinds_registered(cls, group: GroupNodeBlob) -> None:
        """
        Recursively assert every action node's (family, kind) is still in the registry.

        Args:
            group (GroupNodeBlob): The (sub-)graph to walk — nested groups + ForEach bodies included.

        Raises:
            KeyError: Naming the first node whose kind the engine no longer registers (caught by
                ``__heal`` and re-raised as a clear BlobNormalizationError).
        """
        # 1. Walk children: an action is checked against the registry; a group/foreach recurses.
        for node in group.nodes:
            if isinstance(node, ActionNodeBlob):
                NodeRegistry.get(node.family, node.kind)  # raises KeyError if the kind is gone
            elif isinstance(node, ForEachNodeBlob):
                cls.__assert_kinds_registered(node.body)
            elif isinstance(node, GroupNodeBlob):
                cls.__assert_kinds_registered(node)


__all__ = ["BlobNormalizer", "BlobNormalizationError", "ENGINE_BLOB_VERSION"]
