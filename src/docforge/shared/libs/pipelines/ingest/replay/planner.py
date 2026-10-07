# ====== Code Summary ======
# ReplayPlanner — decides, purely from a built ingestion graph, how to replay a document FROM a stage:
# the root node the run starts at, the downstream root nodes it runs, and every upstream (node, field)
# a downstream binding reads — each typed as a persisted artefact the worker can rebuild (the IR, the
# stored chunks, the generated document metadata, the intake facts, the page renders). A replay is
# REFUSED (ReplayUnsupportedError, a data verdict the router maps to 422) when the stage is pre-IR
# (intake/convert/parse/language/render rewrite the IR itself), absent from the pipeline, or when a
# downstream binding needs an artefact that only ever exists in flight (e.g. the RAW pre-contextualize
# chunk text — only the contextualized text is stored). No I/O: the worker loads what the plan names.

# ====== Standard Library Imports ======
from dataclasses import dataclass, field
from enum import StrEnum

# ====== Internal Project Imports ======
from shared_libs.pipelines.base import (
    ActionNode,
    ForEach,
    FromFirst,
    FromNode,
    GraphTopology,
    Group,
)
from shared_libs.pipelines.ingest.stages import StageKey
from shared_libs.public_models import (
    Chunk,
    DocumentIR,
    GeneratedDocumentMeta,
    IntakeResult,
    PageRenders,
)

# ====== Local Project Imports ======
from .stage_map import STAGE_RANK, ReplayStageMap

# The stages a replay may start at — the post-IR stages of the rail (in run order). Pre-IR stages
# rewrite the IR the replay stands on, so they need a full reingest. CONTEXTUALIZE is deliberately
# absent: it always reads the chunker's RAW text, which is never persisted (only the contextualized text
# is), so no shipped pipeline can start there — replay from CHUNK instead.
REPLAYABLE_STAGES: tuple[StageKey, ...] = (
    StageKey.ENRICH,
    StageKey.CHUNK,
    StageKey.METAGEN_CHUNK,
    StageKey.METAGEN_DOCUMENT,
    StageKey.EMBED,
)


class SeedKind(StrEnum):
    """The persisted artefact a seeded upstream slot is rebuilt from."""

    INGEST = "ingest"
    IR = "ir"
    PAGES = "pages"
    CHUNKS = "chunks"
    DOCUMENT_META = "document_meta"


@dataclass(frozen=True, slots=True)
class SeedNeed:
    """
    One upstream output field a downstream binding reads, and how to rebuild it.

    Attributes:
        node_id (str): The upstream root node whose output is seeded.
        field_name (str): The output field the binding reads.
        kind (SeedKind): The persisted artefact to rebuild it from.
        with_language (bool): IR only — the language node ran at/before the producer.
        with_enrichments (bool): IR only — the enrich stage ran at/before the producer (else the
            figure slots are reset to their parse-time placeholders).
        with_generated_meta (bool): Chunks only — chunk-scope metagen ran at/before the producer.
    """

    node_id: str
    field_name: str
    kind: SeedKind
    with_language: bool = False
    with_enrichments: bool = False
    with_generated_meta: bool = False


@dataclass(frozen=True, slots=True)
class ReplayPlan:
    """
    How to replay one stage of a built graph.

    Attributes:
        stage (StageKey): The requested stage.
        start_node_id (str): The root node the run starts at.
        downstream_ids (frozenset[str]): The root nodes the run may execute.
        needs (tuple[SeedNeed, ...]): The upstream outputs to seed.
        needs_crops (bool): The figure crops must be rehydrated (an enrich stage re-runs).
    """

    stage: StageKey
    start_node_id: str
    downstream_ids: frozenset[str]
    needs: tuple[SeedNeed, ...] = field(default_factory=tuple)
    needs_crops: bool = False


class ReplayUnsupportedError(ValueError):
    """A replay request the pipeline cannot honour — the reason is user-facing (422)."""


class ReplayPlanner:
    """Static-only planner: (built graph, stage) → ReplayPlan, or a reasoned refusal."""

    _ARTIFACT_KINDS: dict[object, SeedKind] = {
        IntakeResult: SeedKind.INGEST,
        DocumentIR: SeedKind.IR,
        PageRenders: SeedKind.PAGES,
        list[Chunk]: SeedKind.CHUNKS,
        GeneratedDocumentMeta: SeedKind.DOCUMENT_META,
    }

    def __new__(cls, *args: object, **kwargs: object) -> None:
        raise TypeError("ReplayPlanner is a static-only class and cannot be instantiated.")

    @staticmethod
    def __descendants(group: Group, node_id: str) -> set[str]:
        """Every root id reachable from ``node_id`` through any transition (excluding itself)."""
        seen: set[str] = set()
        stack = [t.to_node_id for t in group.transitions if t.from_node_id == node_id]
        while stack:
            current = stack.pop()
            if current not in seen:
                seen.add(current)
                stack.extend(t.to_node_id for t in group.transitions if t.from_node_id == current)
        return seen

    @staticmethod
    def __upstream_refs(group: Group, downstream: set[str]) -> list[tuple[str, str, str]]:
        """Every (consumer, producer, field) where a downstream root reads an upstream root."""
        refs: list[tuple[str, str, str]] = []
        for child in group.children:
            if child.id not in downstream:
                continue
            bindings = list(group.bindings.get(child.id, {}).values())
            if isinstance(child, ForEach):
                bindings.append(child.over)
            for binding in bindings:
                sources = binding.candidates if isinstance(binding, FromFirst) else [binding]
                for source in sources:
                    if isinstance(source, FromNode) and source.node_id not in downstream:
                        refs.append((child.id, source.node_id, source.field_name))
        return refs

    @classmethod
    def __seed_need(
        cls,
        group: Group,
        stages: dict[str, StageKey | None],
        ancestors: dict[str, set[str]],
        producer_id: str,
        field_name: str,
    ) -> SeedNeed:
        """Type one upstream reference as a persisted artefact, or refuse it with the reason."""
        # 1. The producer must be an action whose output field is a known persisted artefact.
        producer = next(child for child in group.children if child.id == producer_id)
        produces = producer.Produces if isinstance(producer, ActionNode) else None
        info = produces.model_fields.get(field_name) if produces is not None else None
        kind = cls._ARTIFACT_KINDS.get(info.annotation) if info is not None else None
        if kind is None:
            raise ReplayUnsupportedError(
                f"'{producer_id}.{field_name}' is an in-flight artefact that is not persisted"
            )

        # 2. What had already happened at the producer — the fidelity of the persisted rebuild.
        upto = ancestors[producer_id] | {producer_id}
        ran = {stages.get(node_id) for node_id in upto}
        if kind is SeedKind.CHUNKS:
            later = cls.__descendants(group, producer_id)
            if any(stages.get(n) in (StageKey.CHUNK, StageKey.CONTEXTUALIZE) for n in later):
                raise ReplayUnsupportedError(
                    f"'{producer_id}' emits the raw (pre-contextualize) chunk text, which is not "
                    f"persisted — only the final contextualized text is stored; replay from "
                    f"'{StageKey.CHUNK.value}' instead"
                )
        return SeedNeed(
            node_id=producer_id,
            field_name=field_name,
            kind=kind,
            with_language=StageKey.LANGUAGE in ran,
            with_enrichments=StageKey.ENRICH in ran,
            with_generated_meta=StageKey.METAGEN_CHUNK in ran,
        )

    @classmethod
    def __start_node(cls, group: Group, stages: dict[str, StageKey | None], stage: StageKey) -> str:
        """The single node of ``stage`` none of whose ancestors belongs to the same stage."""
        members = {node_id for node_id, key in stages.items() if key is stage}
        if not members:
            raise ReplayUnsupportedError(
                f"stage '{stage.value}' is not enabled in this collection's pipeline"
            )
        ancestors = GraphTopology.ancestors({c.id for c in group.children}, group.transitions)
        heads = [node_id for node_id in members if not (ancestors[node_id] & members)]
        if len(heads) != 1:
            raise ReplayUnsupportedError(f"stage '{stage.value}' has no single entry node")
        return heads[0]

    @classmethod
    def plan(cls, group: Group, stage: StageKey | str) -> ReplayPlan:
        """
        Plan a replay of ``group`` from ``stage``.

        Args:
            group (Group): The built (and validated) root ingestion graph.
            stage (StageKey | str): The stage to replay from.

        Returns:
            ReplayPlan: The start node, the downstream scope and the seeds to rebuild.

        Raises:
            ReplayUnsupportedError: The stage cannot be replayed on this pipeline (reason inside).
        """
        # 1. Only post-IR stages; the stage must exist and have a single head.
        key = StageKey(stage) if stage in {s.value for s in StageKey} else None
        if key not in REPLAYABLE_STAGES:
            hint = (
                f"replay from '{StageKey.CHUNK.value}' instead (the raw chunker text contextualize "
                f"reads is not persisted)"
                if key is StageKey.CONTEXTUALIZE
                else "earlier stages rewrite the persisted IR; use a full reingest"
            )
            raise ReplayUnsupportedError(
                f"'{stage}' is not a replayable stage — replayable: "
                f"{', '.join(s.value for s in REPLAYABLE_STAGES)} ({hint})"
            )
        stages = ReplayStageMap.classify(group)
        start = cls.__start_node(group, stages, key)

        # 2. The downstream scope; every node in it must sit at/after the stage (canonical order).
        downstream = {start} | cls.__descendants(group, start)
        if any(
            STAGE_RANK.get(stages.get(n) or StageKey.INTAKE, 0) < STAGE_RANK[key]
            for n in downstream
        ):
            raise ReplayUnsupportedError(
                f"the pipeline runs a pre-'{key.value}' stage after it; use a full reingest"
            )

        # 3. Type every upstream reference the downstream reads (deduplicated).
        ancestors = GraphTopology.ancestors({c.id for c in group.children}, group.transitions)
        refs = {(producer, name) for _, producer, name in cls.__upstream_refs(group, downstream)}
        needs = tuple(
            cls.__seed_need(group, stages, ancestors, producer, name)
            for producer, name in sorted(refs)
        )
        return ReplayPlan(
            stage=key,
            start_node_id=start,
            downstream_ids=frozenset(downstream),
            needs=needs,
            needs_crops=key is StageKey.ENRICH,
        )

    @classmethod
    def allowed(cls, group: Group) -> list[str]:
        """The stage keys this graph can be replayed from (for the 422 listing and the UI)."""
        allowed: list[str] = []
        for stage in REPLAYABLE_STAGES:
            try:
                cls.plan(group, stage)
            except ReplayUnsupportedError:
                continue
            allowed.append(stage.value)
        return allowed


__all__ = [
    "REPLAYABLE_STAGES",
    "ReplayPlan",
    "ReplayPlanner",
    "ReplayUnsupportedError",
    "SeedKind",
    "SeedNeed",
]
