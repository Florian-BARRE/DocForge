"""SetProvider: every available kind of every provider stage (parse, chunk, embed)."""

import pytest

from shared_libs.pipelines.ingest.stages import SetProvider
from shared_libs.pipelines.registry import NodeRegistry


def _issues(builder, validator, blob) -> list:
    return validator.validate(builder.build(blob))


@pytest.mark.parametrize("kind", NodeRegistry.kinds("chunker"))
def test_chunk_provider_swap_keeps_wiring_and_validates(compiler, builder, validator, kind) -> None:
    from shared_libs.pipelines.ingest import IngestPipeline

    default = IngestPipeline.default_blob()
    swapped, notices = compiler.apply(default, SetProvider(stage="chunk", kind=kind))
    assert _issues(builder, validator, swapped) == [], (kind, notices)
    chunk_node = next(n for n in swapped.nodes if n.id == "chunk")
    assert chunk_node.kind == kind
    # The 'ir' wiring survives the swap untouched.
    assert swapped.bindings["chunk"]["ir"] == default.bindings["chunk"]["ir"]


@pytest.mark.parametrize("kind", NodeRegistry.kinds("embed"))
def test_embed_provider_swap_keeps_wiring_and_validates(compiler, builder, validator, kind) -> None:
    from shared_libs.pipelines.ingest import IngestPipeline

    default = IngestPipeline.default_blob()
    swapped, notices = compiler.apply(default, SetProvider(stage="embed", kind=kind))
    assert _issues(builder, validator, swapped) == [], (kind, notices)
    embed_node = next(n for n in swapped.nodes if n.id == "embed")
    assert embed_node.kind == kind


@pytest.mark.parametrize("kind", NodeRegistry.kinds("parser"))
def test_parse_provider_swap_keeps_wiring_and_validates(compiler, builder, validator, kind) -> None:
    from shared_libs.pipelines.ingest import IngestPipeline

    default = IngestPipeline.default_blob()
    swapped, notices = compiler.apply(default, SetProvider(stage="parse", kind=kind))
    assert _issues(builder, validator, swapped) == [], (kind, notices)
    parse_node = next(n for n in swapped.nodes if n.id == "parse")
    assert parse_node.kind == kind


def test_set_provider_resets_config_to_build_safe_schema_defaults(compiler) -> None:
    from shared_libs.pipelines.ingest import IngestPipeline

    default = IngestPipeline.default_blob()
    swapped, _ = compiler.apply(default, SetProvider(stage="embed", kind="openai_compatible"))
    embed_node = next(n for n in swapped.nodes if n.id == "embed")
    # Required (default-less) fields are completed with build-safe empty values, never absent.
    from shared_libs.pipelines.registry import NodeRegistry as Registry

    node_class = Registry.get("embed", "openai_compatible")
    for name, field in node_class.Config.model_fields.items():
        if field.is_required():
            assert name in embed_node.config, name


def test_set_provider_on_a_non_provider_stage_is_a_clean_notice(compiler) -> None:
    from shared_libs.pipelines.ingest import IngestPipeline

    default = IngestPipeline.default_blob()
    unchanged, notices = compiler.apply(default, SetProvider(stage="render", kind="whatever"))
    assert unchanged == default
    assert notices


def test_set_provider_with_an_unknown_kind_is_a_clean_notice(compiler) -> None:
    from shared_libs.pipelines.ingest import IngestPipeline

    default = IngestPipeline.default_blob()
    unchanged, notices = compiler.apply(default, SetProvider(stage="chunk", kind="does_not_exist"))
    assert unchanged == default
    assert notices
