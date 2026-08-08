# ====== Code Summary ======
# MetagenPrepConfig — the config of a metagen PREP node, which doubles as the metagen STAGE config the
# studio edits. It IS BaseMetagenConfig (the shared metagen config): the default endpoint each
# GenerationRequest inherits, the per-field TARGETS, the grouping knob, the system prompt and the
# generation caps, PLUS the two STAGE-EXECUTION knobs — ``on_error`` and ``max_concurrency`` — that
# became graph mechanics when the model call was externalised into a structgen chain. Those two are NOT
# consumed by the prep's run(): they are read by the stage assembler to shape the ForEach the prep is
# wrapped in (its concurrency) and the fail-soft skip terminal of its body (the on_error edge). This
# module is the studio-facing NAME for that shared config; it re-declares no field (which is what let
# it drift from BaseMetagenConfig before) — it only pins the prep/stage identity onto the same schema.

# ====== Local Project Imports ======
from ..base import BaseMetagenConfig


class MetagenPrepConfig(BaseMetagenConfig):
    """The config of a metagen PREP node — the studio-edited metagen STAGE config (== BaseMetagenConfig)."""


__all__ = ["MetagenPrepConfig"]
