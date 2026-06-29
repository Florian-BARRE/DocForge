# ====== Code Summary ======
# StageKey — the canonical, typed identifier of every pipeline stage. A StrEnum so it interoperates
# transparently with the str-keyed dicts (fingerprints / from_cache) and any remaining string
# comparison, while giving the codebase ONE source of truth for stage identity (replacing the old
# stringly ``KEY`` ClassVar AND the legacy ``NODE_TYPE`` "s0"/"s1"/"s2" cache ids). The node cache +
# Merkle fingerprint now key on this value directly.

# ====== Standard Library Imports ======
from __future__ import annotations

from enum import StrEnum


class StageKey(StrEnum):
    """
    Canonical identifier of a pipeline stage (the node-cache + fingerprint key).

    Values are clean lowercase domain names; ordering here is the declaration order, not the DAG
    order (the DAG is derived from each stage's ``after`` edges).

    Members:
        INGEST: Content-address + convert + upload (was node id "s0").
        PARSE: Parse to the canonical IR (was node id "s1").
        ENRICH: Classify + OCR/VLM/chart enrich the IR (was node id "s2").
        CHUNK: Structure-aware chunking.
        CONTEXTUALIZE: Build each chunk's embed_text.
        METAGEN: LLM-generated per-chunk/per-document metadata.
        EMBED_INDEX: Embed + Qdrant upsert + Postgres persist.
    """

    INGEST = "ingest"
    PARSE = "parse"
    ENRICH = "enrich"
    CHUNK = "chunk"
    CONTEXTUALIZE = "contextualize"
    METAGEN = "metagen"
    EMBED_INDEX = "embed_index"


__all__ = ["StageKey"]
