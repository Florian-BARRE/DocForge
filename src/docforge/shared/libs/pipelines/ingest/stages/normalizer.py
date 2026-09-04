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
        healed, _dropped = cls.normalize_reporting(blob)
        return healed

    @classmethod
    def normalize_reporting(cls, blob: Mapping[str, Any]) -> tuple[dict[str, Any], set[str]]:
        """
        Heal a blob AND report the input node ids the heal could not round-trip.

        The heal reduces a blob to the stage-level surface the StateReader captures and re-emits it
        from that truth. The reader captures ONLY the stage surface (providers, chains, stack, loops,
        configs), so a node the input carried that the reader does not round-trip DISAPPEARS from the
        healed blob. That is exactly a GRAPH-LEVEL customisation made through the headless ``/edit``
        surface with a REGISTERED kind (``add_node`` / ``insert_fragment``): its kind passes
        ``__assert_kinds_registered`` (which only guards kinds the registry no longer knows), yet the
        stage reader never sees it. Returning the dropped ids lets a write boundary REFUSE the save
        instead of silently discarding the customisation — while legitimate re-wiring (bindings and
        transitions the assembler regenerates) and additive migrations (new structural nodes the heal
        ADDS) never appear as a drop, so the normal heal path is untouched.

        Args:
            blob (Mapping): The stored/posted pipeline blob (possibly carrying a version stamp).

        Returns:
            tuple[dict, set[str]]: The current-engine blob (stamp stripped) and the set of input
            node ids the heal dropped (empty on the fast path or when nothing was dropped).

        Raises:
            BlobNormalizationError: The blob cannot be read back into a PipelineState.
        """
        # 1. Fast path — a blob stamped with the current version is already current-shaped: strip
        #    the reserved key (the pure builder forbids extras) and hand it back untouched. Nothing
        #    is healed, so nothing can be dropped.
        clean = {key: value for key, value in blob.items() if key != cls.STAMP_KEY}
        if blob.get(cls.STAMP_KEY) == ENGINE_BLOB_VERSION:
            return clean, set()

        # 2. Heal — round-trip through the stage-level truth to the current engine's topology, then
        #    diff the node-id sets: an input node absent from the healed blob is a customisation the
        #    stage reader could not round-trip (only DROPS count — additive migration ADDS nodes).
        healed = cls.__heal(clean)
        dropped = cls.__node_ids(clean) - cls.__node_ids(healed)
        return healed, dropped

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
    def __node_ids(cls, blob: Mapping[str, Any]) -> set[str]:
        """
        Collect every CHILD node id in a blob, recursing nested groups and ForEach bodies.

        The root container's own id is excluded (only the graph's contents are compared), so a
        differing root id between the input and its healed form never registers as a drop. Walks the
        raw dict rather than the parsed model so it is cheap and shape-tolerant (both a group's
        ``nodes`` and a ForEach's ``body.nodes`` carry children).

        Args:
            blob (Mapping): A blob (or sub-blob) dict whose child node ids are collected.

        Returns:
            set[str]: Every child node id reachable from this blob, at any nesting depth.
        """
        ids: set[str] = set()

        def walk(nodes: list[Any]) -> None:
            for node in nodes:
                if not isinstance(node, Mapping):
                    continue
                node_id = node.get("id")
                if node_id is not None:
                    ids.add(node_id)
                # A nested group exposes its children under ``nodes``; a ForEach under ``body.nodes``.
                walk(node.get("nodes") or [])
                body = node.get("body")
                if isinstance(body, Mapping):
                    walk(body.get("nodes") or [])

        walk(list(blob.get("nodes") or []))
        return ids

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
