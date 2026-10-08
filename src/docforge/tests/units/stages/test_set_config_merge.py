"""SetStageConfig ``mode``: ``replace`` (default, whole-dict) vs ``merge`` ({**current, **patch}, a null
deleting the key) on EVERY StageConfigHandler branch — intake (named node), convert, a chain head (embed) and
a single-config stage (chunk) — plus the chain-rebuild secret carry (same provider only)."""

from shared_libs.pipelines.blob_secrets import MASK
from shared_libs.pipelines.ingest import IngestPipeline
from shared_libs.pipelines.ingest.stages import (
    EnableStage,
    SetChain,
    SetProvider,
    SetStageConfig,
    StateReader,
)
from shared_libs.pipelines.ingest.stages.models import ChainStep


def _apply(compiler, blob, action):
    edited, _ = compiler.apply(blob, action)
    return edited, StateReader.read(edited)


def test_intake_named_node_merge_keeps_other_keys_and_replace_drops_them(compiler) -> None:
    blob = IngestPipeline.default_blob()
    _, merged = _apply(
        compiler, blob, SetStageConfig(stage="intake", node="pdf_probe", config={}, mode="merge")
    )
    assert merged.intake_configs["pdf_probe"] == {"max_pages": 2000}
    _, replaced = _apply(
        compiler, blob, SetStageConfig(stage="intake", node="pdf_probe", config={})
    )
    assert replaced.intake_configs.get("pdf_probe", {}) == {}


def test_convert_merge_overlays_and_null_deletes(compiler) -> None:
    blob = IngestPipeline.default_blob()
    edited, state = _apply(
        compiler,
        blob,
        SetStageConfig(stage="convert", config={"username": "u", "password": "p"}, mode="merge"),
    )
    assert state.intake_configs["convert"] == {
        "base_url": "http://gotenberg:3000",
        "username": "u",
        "password": "p",
    }
    _, state = _apply(
        compiler, edited, SetStageConfig(stage="convert", config={"username": None}, mode="merge")
    )
    assert state.intake_configs["convert"] == {"base_url": "http://gotenberg:3000", "password": "p"}


def test_convert_replace_is_whole_dict(compiler) -> None:
    blob = IngestPipeline.default_blob()
    _, state = _apply(compiler, blob, SetStageConfig(stage="convert", config={"username": "u"}))
    assert state.intake_configs["convert"] == {"username": "u"}


def test_chain_head_slot_merge_keeps_the_api_key(compiler) -> None:
    blob = IngestPipeline.default_blob()
    keyed, _ = _apply(
        compiler,
        blob,
        SetStageConfig(stage="embed", slot="dense", config={"api_key": "sk-live"}, mode="merge"),
    )
    _, state = _apply(
        compiler,
        keyed,
        SetStageConfig(stage="embed", slot="dense", config={"timeout_seconds": 30.0}, mode="merge"),
    )
    dense = state.embed_chain.steps[0].config["dense"]
    assert dense["api_key"] == "sk-live"
    assert dense["base_url"] == "http://bge_server:80"
    assert dense["timeout_seconds"] == 30.0
    # The sibling slot is untouched; replace keeps the slot's kind.
    assert "api_key" not in state.embed_chain.steps[0].config["sparse"]
    _, replaced = _apply(
        compiler,
        keyed,
        SetStageConfig(stage="embed", slot="dense", config={"base_url": "http://x:1"}),
    )
    assert replaced.embed_chain.steps[0].config["dense"] == {
        "base_url": "http://x:1",
        "kind": "bge_server",
    }


def test_single_config_stage_merge_vs_replace(compiler) -> None:
    blob = IngestPipeline.default_blob()
    first, _ = _apply(compiler, blob, SetStageConfig(stage="chunk", config={"a": 1, "b": 2}))
    _, merged = _apply(
        compiler, first, SetStageConfig(stage="chunk", config={"b": None, "c": 3}, mode="merge")
    )
    assert merged.chunker_config == {"a": 1, "c": 3}


def _metagen_keyed(compiler):
    """The default blob with chunk metagen on and its 1-step structgen ladder keyed."""
    blob, _ = compiler.apply(IngestPipeline.default_blob(), EnableStage(stage="metagen_chunk"))
    keyed, _ = compiler.apply(
        blob,
        SetChain(
            stage="metagen_chunk",
            steps=[
                ChainStep(
                    kind="openai_compatible",
                    config={"base_url": "http://llm.example/v1", "api_key": "sk-live"},
                )
            ],
        ),
    )
    return keyed


def test_set_chain_omitted_secret_is_carried_from_the_same_provider_only(compiler) -> None:
    keyed = _metagen_keyed(compiler)
    endpoint = {"base_url": "http://llm.example/v1"}
    # Same kind at the same position + endpoint, key omitted → kept.
    _, same = _apply(
        compiler,
        keyed,
        SetChain(
            stage="metagen_chunk", steps=[ChainStep(kind="openai_compatible", config=endpoint)]
        ),
    )
    assert same.metachunk_chain.steps[0].config["api_key"] == "sk-live"
    # Explicit "" clears.
    _, cleared = _apply(
        compiler,
        keyed,
        SetChain(
            stage="metagen_chunk",
            steps=[ChainStep(kind="openai_compatible", config={**endpoint, "api_key": ""})],
        ),
    )
    assert cleared.metachunk_chain.steps[0].config["api_key"] == ""


def test_set_chain_onto_a_new_host_never_carries_the_secret(compiler) -> None:
    keyed = _metagen_keyed(compiler)
    moved_blob, notices = compiler.apply(
        keyed,
        SetChain(
            stage="metagen_chunk",
            steps=[
                ChainStep(kind="openai_compatible", config={"base_url": "http://evil.example:9"})
            ],
        ),
    )
    head = StateReader.read(moved_blob).metachunk_chain.steps[0].config
    assert head["api_key"] == MASK and "sk-live" not in str(moved_blob.model_dump())
    assert any("must be re-entered" in notice for notice in notices)


def test_embed_slot_provider_repick_keeps_and_swap_drops_the_secret(compiler) -> None:
    keyed, _ = _apply(
        compiler,
        IngestPipeline.default_blob(),
        SetStageConfig(stage="embed", slot="dense", config={"api_key": "sk-live"}, mode="merge"),
    )
    # Re-picking the SAME slot kind keeps the slot (endpoint + key) untouched.
    _, same = _apply(compiler, keyed, SetProvider(stage="embed", slot="dense", kind="bge_server"))
    assert same.embed_chain.steps[0].config["dense"]["api_key"] == "sk-live"
    # Another kind is a fresh slot — the key never follows.
    _, swapped = _apply(
        compiler, keyed, SetProvider(stage="embed", slot="dense", kind="openai_compatible")
    )
    assert "sk-live" not in str(swapped.embed_chain.steps[0].config["dense"])


def test_merge_moving_the_endpoint_drops_the_unrestated_secret(compiler) -> None:
    blob = IngestPipeline.default_blob()
    keyed, _ = _apply(
        compiler,
        blob,
        SetStageConfig(stage="embed", slot="dense", config={"api_key": "sk-live"}, mode="merge"),
    )
    _, moved = _apply(
        compiler,
        keyed,
        SetStageConfig(
            stage="embed", slot="dense", config={"base_url": "http://evil.example:9"}, mode="merge"
        ),
    )
    assert "api_key" not in moved.embed_chain.steps[0].config["dense"]
    _, restated = _apply(
        compiler,
        keyed,
        SetStageConfig(
            stage="embed",
            slot="dense",
            config={"base_url": "http://x:1", "api_key": "sk-x"},
            mode="merge",
        ),
    )
    assert restated.embed_chain.steps[0].config["dense"]["api_key"] == "sk-x"


def test_merge_null_on_a_secret_is_an_explicit_clear(compiler) -> None:
    blob = IngestPipeline.default_blob()
    keyed, _ = _apply(
        compiler,
        blob,
        SetStageConfig(stage="embed", slot="dense", config={"api_key": "sk-live"}, mode="merge"),
    )
    _, cleared = _apply(
        compiler,
        keyed,
        SetStageConfig(stage="embed", slot="dense", config={"api_key": None}, mode="merge"),
    )
    assert cleared.embed_chain.steps[0].config["dense"]["api_key"] == ""
