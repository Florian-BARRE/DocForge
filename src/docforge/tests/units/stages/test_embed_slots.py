"""The embed node's dense / sparse provider SLOTS at the stage layer + the legacy heal.

Pins: a pre-slots stored embed step (bge_server with/without sparse, openai_compatible) heals to the
``(embed, dense_sparse)`` slots it is equivalent to (node-level knobs kept top-level); SetProvider with
a slot switches an axis off / back on, refuses turning BOTH off (a notice, the blob unchanged) and
refuses a kind that cannot fill the slot; SetStageConfig with a slot edits that slot keeping its kind.
"""

import copy

import pytest

from shared_libs.pipelines.build.blob import GroupNodeBlob
from shared_libs.pipelines.ingest.stages import (
    BlobNormalizer,
    IngestAssembler,
    SetProvider,
    SetStageConfig,
    StageViewer,
    StateReader,
    default_state,
)
from shared_libs.pipelines.nodes.embed.dense_sparse import EmbedLegacyMigration

BGE_URL = "http://my-bge:80"


def _legacy_blob(kind: str, config: dict) -> dict:
    """The stock blob, unstamped, with its embed node rewritten to a pre-slots legacy step."""
    blob = copy.deepcopy(IngestAssembler.assemble(default_state()).model_dump(mode="json"))
    embed = next(node for node in blob["nodes"] if node.get("family") == "embed")
    embed["kind"], embed["config"] = kind, config
    return blob


def _embed_head(blob) -> dict:
    """The healed embed chain head's ``(kind, config)`` of a (dict or model) blob."""
    blob = blob if isinstance(blob, dict) else blob.model_dump(mode="json")
    healed = GroupNodeBlob.model_validate(BlobNormalizer.normalize(blob))
    step = StateReader.read(healed).embed_chain.steps[0]
    return {"kind": step.kind, "config": step.config}


# --------------------------------------------------------------------------- legacy heal


def test_legacy_bge_with_sparse_heals_to_one_combined_endpoint_pair() -> None:
    head = _embed_head(
        _legacy_blob(
            "bge_server",
            {"base_url": BGE_URL, "api_key": "k", "model": "bge-m3", "batch_size": 7},
        )
    )
    assert head["kind"] == "dense_sparse"
    slot = {"kind": "bge_server", "base_url": BGE_URL, "api_key": "k", "model": "bge-m3"}
    assert head["config"]["dense"] == slot
    assert head["config"]["sparse"] == slot
    assert head["config"]["batch_size"] == 7


def test_legacy_bge_without_sparse_heals_to_dense_only() -> None:
    head = _embed_head(_legacy_blob("bge_server", {"base_url": BGE_URL, "embed_sparse": False}))
    assert head["config"]["dense"] == {"kind": "bge_server", "base_url": BGE_URL}
    assert head["config"]["sparse"] is None
    assert "embed_sparse" not in head["config"]


def test_legacy_openai_heals_to_dense_only_and_keeps_node_knobs() -> None:
    legacy = {
        "base_url": "http://emb:8000/v1",
        "model": "m",
        "batch_size": 3,
        "embed_semantic_fields": True,
    }
    head = _embed_head(_legacy_blob("openai_compatible", legacy))
    assert head["config"] == {
        "dense": {"kind": "openai_compatible", "base_url": "http://emb:8000/v1", "model": "m"},
        "sparse": None,
        "batch_size": 3,
        "embed_semantic_fields": True,
    }


def test_migration_copies_only_present_keys_and_passes_non_legacy_through() -> None:
    assert EmbedLegacyMigration.config("bge_server", {}) == {
        "dense": {"kind": "bge_server"},
        "sparse": {"kind": "bge_server"},
    }
    untouched = {"dense": None}
    assert EmbedLegacyMigration.step("dense_sparse", untouched) == ("dense_sparse", untouched)


# --------------------------------------------------------------------------- slot actions


@pytest.fixture
def stock(compiler):
    """The stock blob (both slots on the in-stack bge_server)."""
    blob, _ = compiler.apply(
        IngestAssembler.assemble(default_state()), SetProvider(stage="embed", kind="dense_sparse")
    )
    return blob


def test_sparse_slot_off_then_back_on(compiler, builder, validator, stock) -> None:
    off, notices = compiler.apply(stock, SetProvider(stage="embed", slot="sparse", kind=None))
    assert notices == []
    assert _embed_head(off)["config"]["sparse"] is None
    assert validator.validate(builder.build(off)) == []

    on, notices = compiler.apply(off, SetProvider(stage="embed", slot="sparse", kind="bm25_local"))
    assert notices == []
    assert _embed_head(on)["config"]["sparse"]["kind"] == "bm25_local"
    assert validator.validate(builder.build(on)) == []


def test_both_slots_off_is_refused_with_a_notice(compiler, stock) -> None:
    dense_off, _ = compiler.apply(stock, SetProvider(stage="embed", slot="dense", kind=None))
    unchanged, notices = compiler.apply(
        dense_off, SetProvider(stage="embed", slot="sparse", kind=None)
    )
    assert any("the other slot is off too" in n for n in notices)
    # The sparse slot stays on (an omitted slot key reads as the in-stack bge_server).
    assert _embed_head(unchanged)["config"].get("sparse", {}) is not None
    assert _embed_head(unchanged) == _embed_head(dense_off)


def test_kind_that_cannot_fill_the_slot_is_a_notice(compiler, stock) -> None:
    unchanged, notices = compiler.apply(
        stock, SetProvider(stage="embed", slot="dense", kind="bm25_local")
    )
    assert any("is not a dense provider" in n for n in notices)
    assert _embed_head(unchanged) == _embed_head(stock)


def test_repicked_bge_reuses_the_other_slot_endpoint(compiler, stock) -> None:
    edited, _ = compiler.apply(
        stock,
        SetStageConfig(stage="embed", slot="dense", config={"base_url": BGE_URL}, mode="merge"),
    )
    swapped, _ = compiler.apply(
        edited, SetProvider(stage="embed", slot="sparse", kind="bm25_local")
    )
    back, _ = compiler.apply(swapped, SetProvider(stage="embed", slot="sparse", kind="bge_server"))
    config = _embed_head(back)["config"]
    assert config["dense"]["kind"] == "bge_server"
    assert config["sparse"]["base_url"] == config["dense"]["base_url"] == BGE_URL


def test_set_config_on_an_off_slot_is_a_notice(compiler, stock) -> None:
    off, _ = compiler.apply(stock, SetProvider(stage="embed", slot="dense", kind=None))
    _, notices = compiler.apply(
        off, SetStageConfig(stage="embed", slot="dense", config={"model": "x"}, mode="merge")
    )
    assert any("slot is off" in n for n in notices)


def test_view_lists_dense_then_sparse_slots(compiler, stock) -> None:
    off, _ = compiler.apply(stock, SetProvider(stage="embed", slot="dense", kind=None))
    catalog = StageViewer.catalog(StateReader.read(off))
    embed = next(stage for stage in catalog.stages if stage.key == "embed")
    assert [slot.slot for slot in embed.slots] == ["dense", "sparse"]
    assert embed.slots[0].provider is None
    assert embed.slots[1].provider == "bge_server"
    assert "bm25_local" in embed.slots[1].available
    assert "bm25_local" not in embed.slots[0].available
