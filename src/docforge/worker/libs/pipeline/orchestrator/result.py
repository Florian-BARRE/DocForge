# ====== Code Summary ======
# EngineResult dataclass — aggregated output of a DynamicStageEngine pipeline run.
# Kept in its own module so the result type imports lightly, without pulling in
# the engine's dependency tree.

# ====== Standard Library Imports ======
from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from common_libs.pipeline.base.stage.keys import StageKey
    from common_libs.pipeline.ingest.stages.ingest.result import IngestResult
    from common_libs.pipeline.ingest.stages.parsing.result import ParseResult
    from common_libs.pipeline.ingest.stages.enrich.result import EnrichResult
    from common_libs.pipeline.stages.s4_chunk import S4Result
    from common_libs.pipeline.stages.s5_contextualize.core import S5Result
    from common_libs.pipeline.stages.s6_embed_index.core import S6Result


@dataclass(slots=True)
class EngineResult:
    """
    Aggregated output of a dynamic-engine pipeline run (S0 → S1 → S2 → S4 → S5 → S6).

    Carries per-stage results, Merkle fingerprints, and cache hit flags.
    Stage results are None when their stage is disabled or not configured.

    Attributes:
        ingest_result (IngestResult): Ingestion stage output (always present).
        parse_result (ParseResult): Parse stage output (always present).
        enrich_result (EnrichResult | None): Enrichment stage output; None on cache error.
        chunk_result (S4Result | None): Chunking stage output.
        contextualize_result (S5Result | None): Contextualization stage output.
        embed_result (S6Result | None): Embed+index stage output; None when no collection is set.
        stage_fingerprints (dict[StageKey, str]): Per-stage Merkle fingerprints (keyed by StageKey).
        from_cache (dict[StageKey, bool]): Per-stage cache hit flags (keyed by StageKey).
    """

    ingest_result: IngestResult
    parse_result: ParseResult
    enrich_result: EnrichResult | None = None      # None only when a cache error occurs
    chunk_result: S4Result | None = None           # always populated on a successful run
    contextualize_result: S5Result | None = None   # always populated on a successful run
    embed_result: S6Result | None = None           # None when no collection_id is set
    stage_fingerprints: "dict[StageKey, str]" = field(default_factory=dict)
    from_cache: "dict[StageKey, bool]" = field(default_factory=dict)
