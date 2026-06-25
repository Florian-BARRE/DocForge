# ====== Code Summary ======
# EngineResult dataclass — aggregated output of a StageEngine pipeline run.
# Extracted from core.py to allow lightweight imports of the result type
# without pulling in the full orchestrator dependency tree.

# ====== Standard Library Imports ======
from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from common_libs.pipeline.stages.s0_ingest.core import S0Result
    from common_libs.pipeline.stages.s1_parse.core import S1Result
    from common_libs.pipeline.stages.s2_enrich import S2Result
    from common_libs.pipeline.stages.s4_chunk import S4Result
    from common_libs.pipeline.stages.s5_contextualize.core import S5Result
    from common_libs.pipeline.stages.s6_embed_index.core import S6Result


@dataclass(slots=True)
class EngineResult:
    """
    Aggregated output of a StageEngine pipeline run (S0 → S1 → S2 → S4 → S5 → S6).

    Carries per-stage results, Merkle fingerprints, and cache hit flags.
    Stage results are None when their stage is disabled or not configured.

    Attributes:
        s0_result (S0Result): Ingestion stage output (always present).
        s1_result (S1Result): Parse stage output (always present).
        s2_result (S2Result | None): Enrichment stage output; None on cache error.
        s4_result (S4Result | None): Chunking stage output.
        s5_result (S5Result | None): Contextualization stage output.
        s6_result (S6Result | None): Embed+index stage output; None when no collection is set.
        stage_fingerprints (dict[str, str]): Per-stage Merkle fingerprints.
        from_cache (dict[str, bool]): Per-stage cache hit flags.
    """

    s0_result: S0Result
    s1_result: S1Result
    s2_result: S2Result | None = None          # None only when a cache error occurs
    s4_result: S4Result | None = None          # always populated on a successful run
    s5_result: S5Result | None = None          # always populated on a successful run
    s6_result: S6Result | None = None          # None when no collection_id is set
    stage_fingerprints: dict[str, str] = field(default_factory=dict)
    from_cache: dict[str, bool] = field(default_factory=dict)
