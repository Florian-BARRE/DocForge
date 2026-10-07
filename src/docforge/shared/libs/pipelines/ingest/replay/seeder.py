# ====== Code Summary ======
# ReplaySeeder — turns a ReplayPlan plus the persisted artefacts the worker loaded (PersistedArtifacts)
# into the engine's ResumePoint: for each upstream (node, field) the downstream reads, an instance of
# that node's Produces model carrying ONLY that field, rebuilt at the producer's fidelity (the IR with
# or without its figure enrichments / language, the chunks with or without their generated metadata).
# Pure: no I/O, every input is handed in, every output is a fresh copy (a run mutates what it carries).

# ====== Standard Library Imports ======
from dataclasses import dataclass, field
from typing import Any

# ====== Internal Project Imports ======
from shared_libs.pipelines.base import ActionNode, Group, NodeOutput
from shared_libs.pipelines.engine import ResumePoint
from shared_libs.public_models import (
    Chunk,
    DocumentIR,
    FigureEnrichment,
    GeneratedDocumentMeta,
    IntakeResult,
    PageRenders,
)

# ====== Local Project Imports ======
from .planner import ReplayPlan, SeedKind, SeedNeed


@dataclass(slots=True)
class PersistedArtifacts:
    """
    The document's persisted state, rebuilt as pipeline artefacts (loaded by the worker).

    Attributes:
        ingest (IntakeResult): The intake FACTS (hash, format, page count) — no bytes: nothing a
            replayable stage runs reads the PDF/source bytes (only parse/render do).
        ir (DocumentIR): The persisted (enriched) IR, pipeline-scope block ids, crops when loaded.
        chunks (list[Chunk]): The stored final chunks (contextualized text, generated metadata).
        document_meta (GeneratedDocumentMeta): The stored generated document-scope values.
    """

    ingest: IntakeResult
    ir: DocumentIR
    chunks: list[Chunk] = field(default_factory=list)
    document_meta: GeneratedDocumentMeta = field(default_factory=GeneratedDocumentMeta)


class ReplaySeeder:
    """Static-only: (plan, graph, persisted artefacts) → the engine's ResumePoint."""

    def __new__(cls, *args: object, **kwargs: object) -> None:
        raise TypeError("ReplaySeeder is a static-only class and cannot be instantiated.")

    @staticmethod
    def __ir_at(need: SeedNeed, ir: DocumentIR) -> DocumentIR:
        """The IR as the producer emitted it: enrichments/language dropped when not yet run."""
        copy = ir.model_copy(deep=True)
        if not need.with_language:
            copy.language = ""
        if not need.with_enrichments:
            for block in copy.blocks:
                if block.figure is not None:
                    block.figure = FigureEnrichment(crop=block.figure.crop)
        return copy

    @classmethod
    def __value(cls, need: SeedNeed, persisted: PersistedArtifacts) -> Any:
        """The rebuilt value of one seeded field."""
        if need.kind is SeedKind.INGEST:
            return persisted.ingest.model_copy()
        if need.kind is SeedKind.IR:
            return cls.__ir_at(need, persisted.ir)
        if need.kind is SeedKind.PAGES:
            return PageRenders()
        if need.kind is SeedKind.DOCUMENT_META:
            return persisted.document_meta.model_copy(deep=True)
        return [
            chunk.model_copy(
                deep=True,
                update=None if need.with_generated_meta else {"generated_meta": {}},
            )
            for chunk in persisted.chunks
        ]

    @classmethod
    def resume_point(
        cls, plan: ReplayPlan, group: Group, persisted: PersistedArtifacts
    ) -> ResumePoint:
        """
        Build the ResumePoint the engine starts the replay from.

        Args:
            plan (ReplayPlan): The planned replay (start node + seeds).
            group (Group): The built root graph (supplies each producer's Produces model).
            persisted (PersistedArtifacts): The loaded persisted artefacts.

        Returns:
            ResumePoint: Start node, seeded upstream outputs, downstream scope.
        """
        # 1. Group the needed fields per producer node.
        fields: dict[str, dict[str, Any]] = {}
        for need in plan.needs:
            fields.setdefault(need.node_id, {})[need.field_name] = cls.__value(need, persisted)

        # 2. One partial Produces instance per producer — only the read fields are set (the
        #    resolver reads attributes; an unset field reads as missing, failing loudly).
        children = {child.id: child for child in group.children}
        seeded: dict[str, NodeOutput] = {}
        for node_id, values in fields.items():
            producer = children[node_id]
            assert isinstance(producer, ActionNode)
            seeded[node_id] = producer.Produces.model_construct(**values)
        return ResumePoint(
            start_node_id=plan.start_node_id,
            seeded_outputs=seeded,
            downstream_ids=plan.downstream_ids,
        )


__all__ = ["PersistedArtifacts", "ReplaySeeder"]
