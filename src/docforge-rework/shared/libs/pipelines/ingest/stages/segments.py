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
from shared_libs.pipelines.ingest.nodes.metagen.base import MetagenOnError

# ====== Local Project Imports ======
from .contextualize_body import ContextualizeBodyBuilder
from .contextualize_stack import ContextualizeStack
from .enrich_body import EnrichBodyBuilder
from .metagen_body import MetagenBodyBuilder
from .state import ChainSpec, PipelineState


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
                cls.__single(
                    "render", "figures", "render", "figure_render", state.render_config, "ir"
                )
            )
        if state.enrich_on:
            segments.append(cls.__enrich(state))
        segments.append(
            cls.__single(
                "chunk", "chunk", "chunker", state.chunker_kind, state.chunker_config, "chunks"
            )
        )
        if state.stack:
            segments.append(cls.__contextualize(state))
        if state.metachunk_on:
            segments.append(
                cls.__metagen(
                    "metagen_chunk",
                    "meta_chunk",
                    "chunk_prep",
                    "chunk_apply",
                    "chunks",
                    state.metachunk_config,
                    state.metachunk_chain,
                )
            )
        if state.metadoc_on:
            segments.append(
                cls.__metagen(
                    "metagen_document",
                    "meta_doc",
                    "document_prep",
                    "document_apply",
                    "meta",
                    state.metadoc_config,
                    state.metadoc_chain,
                )
            )
        if state.embed_on:
            segments.append(cls.__embed(state))
        segments.append(cls.__single("deliver", "bundle", "deliver", "bundle", {}, "bundle"))
        return segments

    @classmethod
    def __single(
        cls,
        key: str,
        node_id: str,
        family: str,
        kind: str,
        config: dict,
        output_field: str,
        bindings: dict[str, dict] | None = None,
    ) -> Segment:
        """A one-node stage segment (parse, render, chunk, metagen, embed, deliver)."""
        node = ActionNodeBlob(id=node_id, family=family, kind=kind, config=dict(config))
        return Segment(
            key=key,
            head=node_id,
            exits=[node_id],
            nodes=[node],
            transitions=[],
            output=FromNode(node_id=node_id, field_name=output_field),
            bindings=bindings or {},
        )

    @classmethod
    def __intake(cls, state: PipelineState) -> Segment:
        """The fixed 5-node intake chain (probe → admit → convert → pdf_probe → address)."""
        spec = [
            ("probe", "intake", "format_probe"),
            ("admit", "intake", "admission"),
            ("convert", "converter", "gotenberg"),
            ("pdf_probe", "intake", "pdf_probe"),
            ("address", "intake", "content_address"),
        ]
        nodes = [
            ActionNodeBlob(
                id=nid, family=fam, kind=kind, config=dict(state.intake_configs.get(nid, {}))
            )
            for nid, fam, kind in spec
        ]
        ids = [nid for nid, _, _ in spec]
        chain = [
            Transition(from_node_id=a, to_node_id=b) for a, b in zip(ids, ids[1:], strict=False)
        ]
        return Segment(
            key="intake",
            head="probe",
            exits=["address"],
            nodes=nodes,
            transitions=chain,
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
                "parse",
                "parse",
                "parser",
                step.kind,
                dict(step.config),
                "ir",
                bindings={"parse": dict(source)},
            )
        # 2. A fallback chain — the shared builder emits the escalation edges + best-first output.
        fragment = ChainFragmentBuilder.build(
            prefix="parse",
            family="parser",
            steps=[
                ChainStepSpec(kind=s.kind, config=dict(s.config), score_below=s.score_below)
                for s in chain.steps
            ],
            step_inputs=source,
            output_field="ir",
            scored=True,
        )
        return Segment(
            key="parse",
            head=fragment.heads[0],
            exits=fragment.exits,
            nodes=fragment.nodes,
            transitions=fragment.transitions,
            output=fragment.output,
            bindings=fragment.bindings,
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
            return cls.__single(
                "embed", "embed", "embed", step.kind, dict(step.config), "embeddings"
            )
        # 2. A failure-only fallback chain — scored=False, so no ScoreBelow edges are emitted.
        fragment = ChainFragmentBuilder.build(
            prefix="embed",
            family="embed",
            steps=[
                ChainStepSpec(kind=s.kind, config=dict(s.config), score_below=s.score_below)
                for s in chain.steps
            ],
            step_inputs={},
            output_field="embeddings",
            scored=False,
        )
        return Segment(
            key="embed",
            head=fragment.heads[0],
            exits=fragment.exits,
            nodes=fragment.nodes,
            transitions=fragment.transitions,
            output=fragment.output,
        )

    @classmethod
    def __enrich(cls, state: PipelineState) -> Segment:
        """The enrich segment: figure_extract → per_figure loop → enrich_apply."""
        nodes = [
            ActionNodeBlob(id="extract", family="enrich", kind="figure_extract"),
            ForEachNodeBlob(
                id="per_figure",
                over=FromNode(node_id="extract", field_name="figures"),
                item_field="figure",
                max_concurrency=4,
                body=EnrichBodyBuilder.build(state.classify_config, state.chains),
            ),
            ActionNodeBlob(id="apply", family="enrich", kind="enrich_apply"),
        ]
        transitions = [
            Transition(from_node_id="extract", to_node_id="per_figure"),
            Transition(from_node_id="per_figure", to_node_id="apply"),
        ]
        return Segment(
            key="enrich",
            head="extract",
            exits=["apply"],
            nodes=nodes,
            transitions=transitions,
            output=FromNode(node_id="apply", field_name="ir"),
        )

    @classmethod
    def __metagen(
        cls,
        key: str,
        prefix: str,
        prep_kind: str,
        apply_kind: str,
        output_field: str,
        prep_config: dict,
        chain: ChainSpec,
    ) -> Segment:
        """A metagen stage: prep → ForEach(structgen chain [+ skip]) → apply (mirrors __enrich).

        The prep emits one GenerationRequest per call group; the ForEach runs the structgen chain
        per request (a fail-soft skip terminal or a propagating failure per the stage's on_error);
        the apply merges the produced values back. ``max_concurrency`` and ``on_error`` are read off
        the prep config — the stage-execution knobs the assembler shapes the loop/body with.
        """
        prep_id, loop_id, apply_id = f"{prefix}_prep", f"{prefix}_loop", f"{prefix}_apply"
        nodes = [
            ActionNodeBlob(id=prep_id, family="metagen", kind=prep_kind, config=dict(prep_config)),
            ForEachNodeBlob(
                id=loop_id,
                over=FromNode(node_id=prep_id, field_name="requests"),
                item_field="request",
                max_concurrency=int(prep_config.get("max_concurrency", 4)),
                body=MetagenBodyBuilder.build(chain, cls.__on_error(prep_config)),
            ),
            ActionNodeBlob(id=apply_id, family="metagen", kind=apply_kind),
        ]
        transitions = [
            Transition(from_node_id=prep_id, to_node_id=loop_id),
            Transition(from_node_id=loop_id, to_node_id=apply_id),
        ]
        return Segment(
            key=key,
            head=prep_id,
            exits=[apply_id],
            nodes=nodes,
            transitions=transitions,
            output=FromNode(node_id=apply_id, field_name=output_field),
        )

    @staticmethod
    def __on_error(prep_config: dict) -> MetagenOnError:
        """The stage's fail policy read off the prep config (defaults to the fail-soft skip)."""
        raw = prep_config.get("on_error")
        return MetagenOnError(raw) if raw else MetagenOnError.SKIP_FIELDS

    @classmethod
    def __contextualize(cls, state: PipelineState) -> Segment:
        """The ordered contextualize stack segment — simple methods are one node, llm externalises.

        A simple method (doc_meta, breadcrumb, sliding) is a single node. The llm method emits a
        prep → ForEach(over=prep.prompts, item=prompt, generic-llm chain [+ keep_raw]) → apply, with
        internal prep→loop and loop→apply edges; each slot's ``tail`` is then chained onto the next
        slot's ``head``. The chunks spine is threaded centrally by the assembler off each ``output``.
        """
        positions = ContextualizeStack.positions(state)
        nodes: list = []
        transitions: list[Transition] = []
        # 1. Emit each slot's node(s) + its own internal transitions.
        for position in positions:
            if not position.is_llm:
                nodes.append(
                    ActionNodeBlob(
                        id=position.head_id,
                        family="contextualize",
                        kind=position.method.kind,
                        config=dict(position.method.config),
                    )
                )
                continue
            nodes.append(
                ActionNodeBlob(
                    id=position.head_id,
                    family="contextualize",
                    kind="llm",
                    config=dict(position.method.config),
                )
            )
            nodes.append(
                ForEachNodeBlob(
                    id=position.loop_id,
                    over=FromNode(node_id=position.head_id, field_name="prompts"),
                    item_field="prompt",
                    max_concurrency=int(position.method.config.get("max_concurrency", 4)),
                    body=ContextualizeBodyBuilder.build(position.chain, position.on_error),
                )
            )
            nodes.append(
                ActionNodeBlob(id=position.apply_id, family="contextualize", kind="llm_apply")
            )
            transitions.append(
                Transition(from_node_id=position.head_id, to_node_id=position.loop_id)
            )
            transitions.append(
                Transition(from_node_id=position.loop_id, to_node_id=position.apply_id)
            )
        # 2. Chain each slot's tail onto the next slot's head.
        for previous, current in zip(positions, positions[1:], strict=False):
            transitions.append(
                Transition(from_node_id=previous.tail_id, to_node_id=current.head_id)
            )
        return Segment(
            key="contextualize",
            head=positions[0].head_id,
            exits=[positions[-1].tail_id],
            nodes=nodes,
            transitions=transitions,
            output=positions[-1].output,
        )


__all__ = ["Segment", "SegmentBuilder"]
