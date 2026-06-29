# ====== Code Summary ======
# ParseScratch — the in-flight hand-off carried between the parse stage's steps. The parse steps
# build up intermediate state (the degraded/no-parse flag from the chain, the rendered figure-crop
# keys) that is NOT durable PipelineContext fields; rather than widen the context with stage-internal
# keys, the steps thread it through a single mutable scratch object stashed under
# ``ctx.aux[PARSE_SCRATCH_KEY]`` (mirroring how the ingest stage hands off via IngestScratch). The
# final step (markdown) reads the populated scratch to assemble the durable ParseResult.

# ====== Standard Library Imports ======
from __future__ import annotations

from dataclasses import dataclass, field

# Context aux key under which the parse steps share their in-flight scratch.
PARSE_SCRATCH_KEY = "parse_scratch"


@dataclass
class ParseScratch:
    """
    Mutable hand-off accumulated across the parse stage's steps.

    The parse step records whether the chain degraded (no IR produced under
    ``failure_policy=continue``); the figure-render step fills the per-figure crop keys; the
    markdown step reads both to assemble the ParseResult (a degraded run yields ``markdown_key=None``
    and no crops, exactly like the legacy path).

    Attributes:
        degraded (bool): True when the parser chain was exhausted under ``failure_policy=continue``
            (an empty IR was substituted) — the markdown step then skips serialisation/upload.
        figure_crop_keys (dict[str, str]): block_id → object-store key for each rendered figure crop.
    """

    degraded: bool = False
    figure_crop_keys: dict[str, str] = field(default_factory=dict)


__all__ = ["ParseScratch", "PARSE_SCRATCH_KEY"]
