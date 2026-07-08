# ====== Code Summary ======
# SegmentBuilder — turns a PipelineState into the ordered list of stage SEGMENTS the assembler
# flattens and binds. A Segment is one stage's contribution: its nodes, its internal transitions,
# the EXITS the next stage is wired from, the single ``output`` Binding that anchors its downstream
# consumers, and any internal node bindings the stage owns (a chain's per-step consumed face). A
# stock stage is one node with a plain FromNode output; a provider stage may be a scored fallback
# CHAIN (parse today) whose exits are every step and whose output is a best-first FromFirst — so a
# chain can occupy a linear stage slot without any downstream consumer changing. Keeping this layer
# here (segments) apart from the spine-threading (assembler) keeps each file to one responsibility.

# ====== Standard Library Imports ======
from dataclasses import dataclass, field

# ====== Third-Party Library Imports ======
from loggerplusplus import loggerplusplus

# ====== Internal Project Imports ======
from shared_libs.pipelines.base import Binding, FromNode, Transition
from shared_libs.pipelines.build.blob import ActionNodeBlob, ForEachNodeBlob
from shared_libs.pipelines.build.chain import ChainFragmentBuilder, ChainStepSpec

# ====== Local Project Imports ======
from .enrich_body import EnrichBodyBuilder
from .state import PipelineState

# Human ids for the contextualize stack nodes, so the stock stack keeps its historical ids.
_CTX_IDS = {"doc_meta": "ctx_meta", "breadcrumb": "ctx_breadcrumb", "sliding": "ctx_sliding",
            "llm": "ctx_llm"}


@dataclass(frozen=True)
class Segment:
    """One stage's contribution to the blob: its ordered nodes, transitions and downstream anchor.

    A segment exposes ``exits`` (not a single tail): the node ids the next stage must be wired
    from. A stock single-node stage has ``exits == [its node]``; a chain occupying a stage slot
    may expose several exits, one per provider step that can be the one that ran. ``output`` is the
    SINGLE source of truth for the stage's downstream anchor — a plain ``FromNode`` for a stock
    stage, the chain's best-first ``FromFirst`` for a chain — so exits and the convergence binding
    can never drift. ``bindings`` carries the stage's own internal node bindings (a chain's per-step
    consumed face); the spine/cross-stage bindings are threaded centrally by the assembler.

    Attributes:
        key (str): The stage key this segment realises.
        head (str): The node id an incoming edge routes into.
        exits (list[str]): The node ids the next stage is wired from.
        nodes (list): The segment's nodes (action / foreach blobs).
        transitions (list): The segment's internal transitions.
        output (Binding): The downstream anchor of the stage (FromNode or FromFirst).
        bindings (dict[str, dict]): The stage's own internal node bindings.
    """

    key: str
    head: str
    exits: list[str]
    nodes: list
    transitions: list
    output: Binding
    bindings: dict[str, dict] = field(default_factory=dict)


class SegmentBuilder:
    """Static builder of the ordered stage segments of an ingestion blob from a PipelineState."""

    logger = loggerplusplus.bind(identifier="SegmentBuilder")

    def __new__(cls, *args: object, **kwargs: object) -> None:
        raise TypeError("SegmentBuilder is a static-only class and cannot be instantiated.")

    @classmethod
    def all(cls, state: PipelineState) -> list[Segment]:
        """
        Build the ordered segment of every ENABLED stage, in canonical run order.

        Args:
            state (PipelineState): The canonical pipeline state to lay out.

        Returns:
            list[Segment]: The stage segments, in the order they run.
        """
        segments = [cls.__intake(state), cls.__parse(state)]
        if state.render_on:
            segments.append(
                cls.__single("render", "figures", "render", "figure_render", state.render_config, "ir")
            )
        if state.enrich_on:
            segments.append(cls.__enrich(state))
        segments.append(
            cls.__single("chunk", "chunk", "chunker", state.chunker_kind, state.chunker_config, "chunks")
        )
        if state.stack:
            segments.append(cls.__contextualize(state))
        if state.metachunk_on:
            segments.append(
                cls.__single("metagen_chunk", "meta_chunk", "metagen", "chunk", state.metachunk_config, "chunks")
            )
        if state.metadoc_on:
            segments.append(
                cls.__single("metagen_document", "meta_doc", "metagen", "document", state.metadoc_config, "meta")
            )
        if state.embed_on:
            segments.append(cls.__embed(state))
        segments.append(cls.__single("deliver", "bundle", "deliver", "bundle", {}, "bundle"))
        return segments

    @classmethod
    def contextualize_ids(cls, state: PipelineState) -> list[str]:
        """The node ids of the contextualize stack, in order (unique per method occurrence)."""
        ids: list[str] = []
        for method in state.stack:
            base = _CTX_IDS.get(method.kind, f"ctx_{method.kind}")
            candidate, suffix = base, 2
            while candidate in ids:
                candidate = f"{base}_{suffix}"
                suffix += 1
            ids.append(candidate)
        return ids

    @classmethod
    def __single(
        cls, key: str, node_id: str, family: str, kind: str, config: dict, output_field: str,
        bindings: dict[str, dict] | None = None,
    ) -> Segment:
        """A one-node stage segment (parse, render, chunk, metagen, embed, deliver)."""
        node = ActionNodeBlob(id=node_id, family=family, kind=kind, config=dict(config))
        return Segment(
            key=key, head=node_id, exits=[node_id], nodes=[node], transitions=[],
            output=FromNode(node_id=node_id, field_name=output_field),
            bindings=bindings or {},
        )

    @classmethod
    def __intake(cls, state: PipelineState) -> Segment:
        """The fixed 5-node intake chain (probe → admit → convert → pdf_probe → address)."""
        spec = [("probe", "intake", "format_probe"), ("admit", "intake", "admission"),
                ("convert", "converter", "gotenberg"), ("pdf_probe", "intake", "pdf_probe"),
                ("address", "intake", "content_address")]
        nodes = [
            ActionNodeBlob(id=nid, family=fam, kind=kind, config=dict(state.intake_configs.get(nid, {})))
            for nid, fam, kind in spec
        ]
        ids = [nid for nid, _, _ in spec]
        chain = [Transition(from_node_id=a, to_node_id=b) for a, b in zip(ids, ids[1:], strict=False)]
        return Segment(
            key="intake", head="probe", exits=["address"], nodes=nodes, transitions=chain,
            output=FromNode(node_id="address", field_name="ingest"),
        )

    @classmethod
    def __parse(cls, state: PipelineState) -> Segment:
        """The parser stage — a 1-step chain is a lone ``parse`` node; >1 step is a scored chain."""
        chain = state.parse_chain
        source = {"source": FromNode(node_id="address", field_name="ingest")}
        # 1. A single provider stays exactly the stock lone node (byte-identical default).
        if len(chain.steps) == 1:
            step = chain.steps[0]
            return cls.__single(
                "parse", "parse", "parser", step.kind, dict(step.config), "ir",
                bindings={"parse": dict(source)},
            )
        # 2. A fallback chain — the shared builder emits the escalation edges + best-first output.
        fragment = ChainFragmentBuilder.build(
            prefix="parse", family="parser",
            steps=[ChainStepSpec(kind=s.kind, config=dict(s.config), score_below=s.score_below)
                   for s in chain.steps],
            step_inputs=source, output_field="ir", scored=True,
        )
        return Segment(
            key="parse", head=fragment.heads[0], exits=fragment.exits, nodes=fragment.nodes,
            transitions=fragment.transitions, output=fragment.output, bindings=fragment.bindings,
        )

    @classmethod
    def __embed(cls, state: PipelineState) -> Segment:
        """The embedder stage — a 1-step chain is a lone ``embed`` node; >1 step is a chain.

        Embed is NON-scored: the fragment escalates on failure only (no ScoreBelow). Unlike parse,
        the consumed face (the chunks spine + contract) depends on which chunks-spine stages are
        enabled, so it is NOT known here — the assembler threads it onto every step id centrally.
        """
        chain = state.embed_chain
        # 1. A single provider stays exactly the stock lone node (byte-identical default).
        if len(chain.steps) == 1:
            step = chain.steps[0]
            return cls.__single("embed", "embed", "embed", step.kind, dict(step.config), "embeddings")
        # 2. A failure-only fallback chain — scored=False, so no ScoreBelow edges are emitted.
        fragment = ChainFragmentBuilder.build(
            prefix="embed", family="embed",
            steps=[ChainStepSpec(kind=s.kind, config=dict(s.config), score_below=s.score_below)
                   for s in chain.steps],
            step_inputs={}, output_field="embeddings", scored=False,
        )
        return Segment(
            key="embed", head=fragment.heads[0], exits=fragment.exits, nodes=fragment.nodes,
            transitions=fragment.transitions, output=fragment.output,
        )

    @classmethod
    def __enrich(cls, state: PipelineState) -> Segment:
        """The enrich segment: figure_extract → per_figure loop → enrich_apply."""
        nodes = [
            ActionNodeBlob(id="extract", family="enrich", kind="figure_extract"),
            ForEachNodeBlob(
                id="per_figure",
                over=FromNode(node_id="extract", field_name="figures"),
                item_field="figure", max_concurrency=4,
                body=EnrichBodyBuilder.build(state.classify_config, state.chains),
            ),
            ActionNodeBlob(id="apply", family="enrich", kind="enrich_apply"),
        ]
        transitions = [
            Transition(from_node_id="extract", to_node_id="per_figure"),
            Transition(from_node_id="per_figure", to_node_id="apply"),
        ]
        return Segment(
            key="enrich", head="extract", exits=["apply"], nodes=nodes, transitions=transitions,
            output=FromNode(node_id="apply", field_name="ir"),
        )

    @classmethod
    def __contextualize(cls, state: PipelineState) -> Segment:
        """The ordered contextualize stack segment (each method chained onto the previous)."""
        ids = cls.contextualize_ids(state)
        nodes = [
            ActionNodeBlob(id=nid, family="contextualize", kind=method.kind, config=dict(method.config))
            for nid, method in zip(ids, state.stack, strict=True)
        ]
        chain = [Transition(from_node_id=a, to_node_id=b) for a, b in zip(ids, ids[1:], strict=False)]
        return Segment(
            key="contextualize", head=ids[0], exits=[ids[-1]], nodes=nodes, transitions=chain,
            output=FromNode(node_id=ids[-1], field_name="chunks"),
        )


__all__ = ["Segment", "SegmentBuilder"]
