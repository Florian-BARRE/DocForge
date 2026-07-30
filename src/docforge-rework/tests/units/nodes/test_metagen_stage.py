"""Metagen family helper coverage: the scope-aware auto-prompt.

The old monolithic metagen nodes are gone (P5c): their grouping / strict-coercion / merge-not-clobber
/ loud-target behaviour is now proven by the externalised topology (test_metagen_topology.py) and the
generic structured-generation capability (test_structgen.py). What stays UNIQUE to the metagen family
is the generative, scope-aware auto-prompt wording — kept here.
"""

from shared_libs.pipelines.ingest.nodes.metagen.base.helpers import MetagenHelpers
from shared_libs.public_models import FieldOrigin, FieldScope, FieldType, MetadataFieldSpec


def _spec(name: str, field_type: FieldType, scope: FieldScope) -> MetadataFieldSpec:
    return MetadataFieldSpec(
        field_name=name, field_type=field_type, origin=FieldOrigin.GENERATED, scope=scope
    )


def test_auto_prompt_is_generative_and_scope_aware() -> None:
    doc_spec = _spec("summary", FieldType.STRING, FieldScope.DOCUMENT)
    chunk_spec = _spec("keywords", FieldType.KEYWORD_LIST, FieldScope.CHUNK)

    doc_prompt = MetagenHelpers.auto_prompt(doc_spec, FieldScope.DOCUMENT)
    chunk_prompt = MetagenHelpers.auto_prompt(chunk_spec, FieldScope.CHUNK)

    # 1. Generative, not extractive: the model must synthesize, never copy a span.
    for prompt in (doc_prompt, chunk_prompt):
        assert "extract" not in prompt.lower()
        assert "from the text" not in prompt.lower()
        assert prompt.startswith("Generate ")

    # 2. Scope-aware: each prompt names its own granularity.
    assert "document" in doc_prompt and "chunk" not in doc_prompt
    assert "chunk" in chunk_prompt and "document" not in chunk_prompt
