# ====== Code Summary ======
# Unit tests for the PR-2 stage registry + DAG primitives (topo_order / validate_wiring).
# Covers: the registered ingest adapters topo-sort to the canonical S0..S6 order and validate;
# unknown AFTER dependency + dependency cycle raise StageWiringError; the CONSUMES/PRODUCES
# wiring validator raises on an unproduced input and on an unknown context key. All in-memory.

# ====== Standard Library Imports ======
from typing import Any

# ====== Third-Party Library Imports ======
import pytest

# ====== Internal Project Imports ======
from common_libs.pipeline.assembly.stage_registry import (
    StageWiringError,
    auto_import_stages,
    get_stages,
    topo_order,
    validate_wiring,
)
from common_libs.pipeline.base import AbstractStage, CachePolicy, ErrorPolicy, StageKey, StageSpec


def _mk_stage(
    key: StageKey,
    after: tuple[StageKey, ...] = (),
    consumes: tuple[str, ...] = (),
    produces: tuple[str, ...] = (),
) -> type[AbstractStage]:
    """
    Build a throwaway concrete AbstractStage subclass declaring the given wiring.

    ``key``/``after`` are StageKey (stage identity + DAG edges); ``consumes``/``produces`` are plain
    str PipelineContext field names — the StageKey-vs-context-key boundary the registry validates.
    """
    spec = StageSpec(
        key=key, name=str(key), description="", after=tuple(after), consumes=tuple(consumes),
        produces=tuple(produces), cache_policy=CachePolicy.NODE_CACHED, error_policy=ErrorPolicy.FAIL_DOC,
    )
    namespace: dict[str, Any] = {"SPEC": spec, "steps": property(lambda self: [])}
    return type(f"_Stage_{key.value}", (AbstractStage,), namespace)


# ─── topo_order ──────────────────────────────────────────────────────────────────


class TestTopoOrder:
    """Kahn ordering by AFTER, with cycle + unknown-dep detection."""

    def test_orders_by_after(self) -> None:
        a = _mk_stage(StageKey.INGEST)
        b = _mk_stage(StageKey.PARSE, after=(StageKey.INGEST,))
        c = _mk_stage(StageKey.ENRICH, after=(StageKey.PARSE,))
        # Pass out of order to prove sorting (not input order) drives the result.
        ordered = topo_order([c, a, b])
        assert [s.SPEC.key for s in ordered] == [StageKey.INGEST, StageKey.PARSE, StageKey.ENRICH]

    def test_unknown_dependency_raises(self) -> None:
        # Only PARSE is registered; its AFTER points at an absent stage → unknown dependency.
        orphan = _mk_stage(StageKey.PARSE, after=(StageKey.METAGEN,))
        with pytest.raises(StageWiringError):
            topo_order([orphan])

    def test_cycle_raises(self) -> None:
        p = _mk_stage(StageKey.INGEST, after=(StageKey.PARSE,))
        q = _mk_stage(StageKey.PARSE, after=(StageKey.INGEST,))
        with pytest.raises(StageWiringError):
            topo_order([p, q])

    def test_registered_adapters_topo_to_canonical_order(self) -> None:
        auto_import_stages()
        ordered = topo_order(list(get_stages().values()))
        assert [str(s.SPEC.key) for s in ordered] == [
            "ingest", "parse", "enrich", "chunk", "contextualize", "metagen", "embed_index",
        ]


# ─── validate_wiring ─────────────────────────────────────────────────────────────


class TestValidateWiring:
    """The IO graph validator folds produced keys and rejects broken graphs."""

    def test_consuming_a_root_input_is_valid(self) -> None:
        # original_bytes is a root context key → consuming it without an upstream producer is fine.
        s = _mk_stage(StageKey.INGEST, consumes=("original_bytes",), produces=("ingest_result",))
        validate_wiring([s])  # must not raise

    def test_consuming_unproduced_key_raises(self) -> None:
        # 'ir' is a real context field but no upstream stage (and no root) produces it.
        s = _mk_stage(StageKey.CHUNK, consumes=("ir",), produces=("chunks",))
        with pytest.raises(StageWiringError):
            validate_wiring([s])

    def test_unknown_context_key_raises(self) -> None:
        s = _mk_stage(StageKey.INGEST, produces=("not_a_context_field",))
        with pytest.raises(StageWiringError):
            validate_wiring([s])

    def test_full_chain_validates(self) -> None:
        # A produces -> B consumes A's output across the order is accepted.
        first = _mk_stage(StageKey.INGEST, consumes=("original_bytes",), produces=("ingest_result",))
        second = _mk_stage(StageKey.PARSE, after=(StageKey.INGEST,), consumes=("ingest_result",), produces=("ir",))
        validate_wiring(topo_order([first, second]))  # must not raise

    def test_registered_adapter_graph_is_valid(self) -> None:
        auto_import_stages()
        validate_wiring(topo_order(list(get_stages().values())))  # the real graph is closed
