# ====== Code Summary ======
# Contract-level enumerations shared by every pipeline node — the serialisable vocabulary the engine
# and the self-describing API speak: the NodeKind discriminator (pipeline/stage/step), the canonical
# StageKey identity, and the two declarative policy enums (CachePolicy / ErrorPolicy) the engine
# middleware reads. StrEnum members serialise to plain strings. Pure standard library — bottom of the
# dependency DAG, imports nothing internal.

# ====== Standard Library Imports ======
from enum import StrEnum


class NodeKind(StrEnum):
    """
    Discriminator for the three levels of the recursive node tree.

    Members:
        PIPELINE: A top-level composite node whose children are stages.
        STAGE: A composite node whose children are steps.
        STEP: A leaf node that performs the actual work.
    """

    PIPELINE = "pipeline"
    STAGE = "stage"
    STEP = "step"


class StageKey(StrEnum):
    """
    Canonical identifier of a stage — the node-cache + fingerprint key for stages.

    Values are clean lowercase domain names; the order here is declaration order, NOT execution
    order (the DAG is derived from each node's input bindings, never from this enum's order).

    Members:
        INGEST: Content-address + convert + upload the original.
        PARSE: Parse the original into the canonical IR.
        ENRICH: Classify + OCR/VLM/chart-enrich the IR.
        CHUNK: Structure-aware chunking.
        CONTEXTUALIZE: Build each chunk's embed text.
        METAGEN: LLM-generated per-chunk / per-document metadata.
        EMBED_INDEX: Embed + Qdrant upsert + Postgres persist.
    """

    INGEST = "ingest"
    PARSE = "parse"
    ENRICH = "enrich"
    CHUNK = "chunk"
    CONTEXTUALIZE = "contextualize"
    METAGEN = "metagen"
    EMBED_INDEX = "embed_index"


class CachePolicy(StrEnum):
    """
    Declarative cache policy read by the engine's caching middleware.

    Members:
        NODE_CACHED: Cached in the Merkle-DAG node cache, keyed by the node fingerprint.
        IDEMPOTENT_WRITE: Not node-cached; idempotency comes from Postgres/Qdrant upserts.
        NONE: Never cached (always re-run).
    """

    NODE_CACHED = "node_cached"
    IDEMPOTENT_WRITE = "idempotent_write"
    NONE = "none"


class ErrorPolicy(StrEnum):
    """
    Declarative error policy read by the engine when a node fails.

    The policy is authoritative: a node's own custom error may *suggest* a behaviour, but the
    declared policy decides what the engine does.

    Members:
        FAIL: Fail-closed — propagate so the parent (ultimately the run) fails.
        SKIP: Skip the node and continue the run; the node produced no output.
        DEGRADE: Continue the run in a degraded state; the node may have partial output.
    """

    FAIL = "fail"
    SKIP = "skip"
    DEGRADE = "degrade"


__all__ = ["NodeKind", "StageKey", "CachePolicy", "ErrorPolicy"]
