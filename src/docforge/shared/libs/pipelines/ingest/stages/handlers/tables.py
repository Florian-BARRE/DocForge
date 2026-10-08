# ====== Code Summary ======
# The stage-key → PipelineState field tables shared by the stage-action handlers. They are the single
# place that says which stages toggle, which carry a provider, which ARE a fallback chain, which carry
# a metagen ladder and which expose one editable config field.

# ====== Local Project Imports ======
from ..spec import StageKey

# Stage key → the PipelineState boolean that toggles it.
TOGGLES = {
    StageKey.LANGUAGE: "language_on",
    StageKey.RENDER: "render_on",
    StageKey.ENRICH: "enrich_on",
    StageKey.METAGEN_CHUNK: "metachunk_on",
    StageKey.METAGEN_DOCUMENT: "metadoc_on",
    StageKey.EMBED: "embed_on",
}

# Stage key → (state field for the provider kind, state field for its config). Parse and embed are
# NOT here: they are fallback chains, so SetProvider is sugar for a 1-step chain (see
# StageProviderHandler).
PROVIDERS = {
    StageKey.CHUNK: ("chunker_kind", "chunker_config"),
}

# Chain-capable linear stages → (state field holding the ChainSpec, the registry family). These are
# provider stages whose provider is a fallback chain, edited with a slot-less SetChain. Parse is
# scored (ScoreBelow escalation); embed is not (failure-only) — the family's scored flag decides.
CHAIN_STAGES = {
    StageKey.PARSE: ("parse_chain", "parser"),
    StageKey.EMBED: ("embed_chain", "embed"),
}

# Metagen chains → (state field holding the structgen ChainSpec, the family). Unlike CHAIN_STAGES
# these are NOT provider stages: metagen is a TOGGLE whose editable config is the PREP endpoint
# (CONFIGS), while its model ladder is a slot-less SetChain over the structgen family (non-scored,
# so score thresholds are dropped). Kept apart so set_config keeps hitting the prep config, and only
# set_chain reaches the ladder.
METAGEN_CHAINS = {
    StageKey.METAGEN_CHUNK: ("metachunk_chain", "structgen"),
    StageKey.METAGEN_DOCUMENT: ("metadoc_chain", "structgen"),
}

# Stage key → the state config field its primary node exposes (chain stages edit their chain head).
CONFIGS = {
    StageKey.LANGUAGE: "language_config",
    StageKey.RENDER: "render_config",
    StageKey.ENRICH: "classify_config",
    StageKey.CHUNK: "chunker_config",
    StageKey.METAGEN_CHUNK: "metachunk_config",
    StageKey.METAGEN_DOCUMENT: "metadoc_config",
}
