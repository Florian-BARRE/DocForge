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
from common_libs.pipeline.base import AbstractStage, CachePolicy, ErrorPolicy


def _mk_stage(
    key: str,
    after: tuple[str, ...] = (),
    consumes: tuple[str, ...] = (),
    produces: tuple[str, ...] = (),
) -> type[AbstractStage]:
    """Build a throwaway concrete AbstractStage subclass declaring the given wiring."""
    namespace: dict[str, Any] = {
        "KEY": key,
        "NAME": key,
        "DESCRIPTION": "",
        "AFTER": tuple(after),
        "CONFIG": None,
        "CONSUMES": tuple(consumes),
        "PRODUCES": tuple(produces),
        "CACHE_POLICY": CachePolicy.NODE_CACHED,
        "ON_ERROR": ErrorPolicy.FAIL_DOC,
        "steps": property(lambda self: []),
    }
    return type(f"_Stage_{key}", (AbstractStage,), namespace)


# ─── topo_order ──────────────────────────────────────────────────────────────────


class TestTopoOrder:
    """Kahn ordering by AFTER, with cycle + unknown-dep detection."""

    def test_orders_by_after(self) -> None:
        a = _mk_stage("a")
        b = _mk_stage("b", after=("a",))
        c = _mk_stage("c", after=("b",))
        # Pass out of order to prove sorting (not input order) drives the result.
        ordered = topo_order([c, a, b])
        assert [s.KEY for s in ordered] == ["a", "b", "c"]

    def test_unknown_dependency_raises(self) -> None:
        orphan = _mk_stage("x", after=("does_not_exist",))
        with pytest.raises(StageWiringError):
            topo_order([orphan])

    def test_cycle_raises(self) -> None:
        p = _mk_stage("p", after=("q",))
        q = _mk_stage("q", after=("p",))
        with pytest.raises(StageWiringError):
            topo_order([p, q])

    def test_registered_adapters_topo_to_canonical_order(self) -> None:
        auto_import_stages()
        ordered = topo_order(list(get_stages().values()))
        assert [s.KEY for s in ordered] == [
            "ingest", "parse", "enrich", "chunk", "contextualize", "metagen", "embed_index",
        ]


# ─── validate_wiring ─────────────────────────────────────────────────────────────


class TestValidateWiring:
    """The IO graph validator folds produced keys and rejects broken graphs."""

    def test_consuming_a_root_input_is_valid(self) -> None:
        # file_bytes is a root context key → consuming it without an upstream producer is fine.
        s = _mk_stage("s", consumes=("file_bytes",), produces=("s0_result",))
        validate_wiring([s])  # must not raise

    def test_consuming_unproduced_key_raises(self) -> None:
        # 'ir' is a real context field but no upstream stage (and no root) produces it.
        s = _mk_stage("s", consumes=("ir",), produces=("chunks",))
        with pytest.raises(StageWiringError):
            validate_wiring([s])

    def test_unknown_context_key_raises(self) -> None:
        s = _mk_stage("s", produces=("not_a_context_field",))
        with pytest.raises(StageWiringError):
            validate_wiring([s])

    def test_full_chain_validates(self) -> None:
        # A produces -> B consumes A's output across the order is accepted.
        first = _mk_stage("first", consumes=("file_bytes",), produces=("s0_result",))
        second = _mk_stage("second", after=("first",), consumes=("s0_result",), produces=("ir",))
        validate_wiring(topo_order([first, second]))  # must not raise

    def test_registered_adapter_graph_is_valid(self) -> None:
        auto_import_stages()
        validate_wiring(topo_order(list(get_stages().values())))  # the real graph is closed
