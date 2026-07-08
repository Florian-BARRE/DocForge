# ====== Code Summary ======
# IngestAssembler — turns a PipelineState into a validated-shape ingestion blob. It is the SINGLE
# owner of the pipeline's wiring: it lays the enabled stages out as a linear control-flow chain and
# threads the DATA SPINES (the IR spine parse→render→enrich, the chunks spine chunk→contextualize→
# metagen) so every consumer always reads the nearest enabled producer. A stage contributes a
# _Segment exposing its EXITS (the nodes the next stage is wired from) and each spine anchor is a
# Binding, not a bare (node, field) tuple — so a multi-exit provider chain can occupy a linear
# stage slot (later phases) without any consumer changing. Because the assembler recomputes wiring
# from the enabled set, the compiler can toggle any stage and still emit a blob that builds: the
# "no doubt, coherent end to end" guarantee lives here. default_blob() is just assemble(default_state()).

# ====== Third-Party Library Imports ======
from loggerplusplus import loggerplusplus

# ====== Internal Project Imports ======
from shared_libs.pipelines.base import Binding, FromNode, FromRunInput, Transition
from shared_libs.pipelines.build.blob import ActionNodeBlob, ForEachNodeBlob, GroupNodeBlob

# ====== Local Project Imports ======
from .enrich_body import EnrichBodyBuilder
from .state import PipelineState

# The run-input field names the entry nodes bind to (kept local to avoid importing the pipeline).
_SOURCE = "source"
_CONTRACT = "contract"

# Human ids for the contextualize stack nodes, so the stock stack keeps its historical ids.
_CTX_IDS = {"doc_meta": "ctx_meta", "breadcrumb": "ctx_breadcrumb", "sliding": "ctx_sliding",
            "llm": "ctx_llm"}


class _Segment:
    """One stage's contribution to the blob: its ordered nodes and internal transitions.

    A segment exposes ``exits`` (not a single tail): the node ids the next stage must be wired
    from. A stock single-node stage has ``exits == [its node]``; a chain occupying a stage slot
    (later phases) may expose several exits, one per provider step that can be the one that ran.
    """

    def __init__(self, head: str, exits: list[str], nodes: list, transitions: list) -> None:
        self.head = head
        self.exits = exits
        self.nodes = nodes
        self.transitions = transitions


class IngestAssembler:
    """Static assembler of an ingestion blob from a PipelineState (the wiring lives here)."""

    logger = loggerplusplus.bind(identifier="IngestAssembler")

    def __new__(cls, *args: object, **kwargs: object) -> None:
        raise TypeError("IngestAssembler is a static-only class and cannot be instantiated.")

    @classmethod
    def assemble(cls, state: PipelineState) -> GroupNodeBlob:
        """
        Assemble the full ingestion blob for a state (nodes, control flow and data spines).

        Args:
            state (PipelineState): The canonical pipeline state to serialise.

        Returns:
            GroupNodeBlob: A blob whose enabled stages are chained and correctly bound.
        """
        # 1. Build the segment of every ENABLED stage, in canonical order.
        segments = cls.__segments(state)

        # 2. Flatten nodes + internal transitions, then chain each segment's exits → next head.
        nodes: list = []
        transitions: list[Transition] = []
        for segment in segments:
            nodes.extend(segment.nodes)
            transitions.extend(segment.transitions)
        for previous, current in zip(segments, segments[1:], strict=False):
            for exit_id in previous.exits:
                transitions.append(Transition(from_node_id=exit_id, to_node_id=current.head))

        # 3. Thread the data spines across whichever stages are on.
        bindings = cls.__bindings(state)
        return GroupNodeBlob(id="ingest_pipeline", nodes=nodes, transitions=transitions,
                             bindings=bindings)

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
    def __segments(cls, state: PipelineState) -> list[_Segment]:
        """The ordered segments of the enabled stages."""
        segments = [cls.__intake(state), cls.__parse(state)]
        if state.render_on:
            segments.append(cls.__single("figures", "render", "figure_render", state.render_config))
        if state.enrich_on:
            segments.append(cls.__enrich(state))
        segments.append(cls.__single("chunk", "chunker", state.chunker_kind, state.chunker_config))
        if state.stack:
            segments.append(cls.__contextualize(state))
        if state.metachunk_on:
            segments.append(cls.__single("meta_chunk", "metagen", "chunk", state.metachunk_config))
        if state.metadoc_on:
            segments.append(cls.__single("meta_doc", "metagen", "document", state.metadoc_config))
        if state.embed_on:
            segments.append(cls.__single("embed", "embed", state.embed_kind, state.embed_config))
        segments.append(cls.__single("bundle", "deliver", "bundle", {}))
        return segments

    @classmethod
    def __single(cls, node_id: str, family: str, kind: str, config: dict) -> _Segment:
        """A one-node stage segment (parse, render, chunk, metagen, embed, deliver)."""
        node = ActionNodeBlob(id=node_id, family=family, kind=kind, config=dict(config))
        return _Segment(head=node_id, exits=[node_id], nodes=[node], transitions=[])

    @classmethod
    def __intake(cls, state: PipelineState) -> _Segment:
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
        return _Segment(head="probe", exits=["address"], nodes=nodes, transitions=chain)

    @classmethod
    def __parse(cls, state: PipelineState) -> _Segment:
        """The parser stage (its own segment so its kind stays selectable)."""
        return cls.__single("parse", "parser", state.parser_kind, state.parser_config)

    @classmethod
    def __enrich(cls, state: PipelineState) -> _Segment:
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
        return _Segment(head="extract", exits=["apply"], nodes=nodes, transitions=transitions)

    @classmethod
    def __contextualize(cls, state: PipelineState) -> _Segment:
        """The ordered contextualize stack segment (each method chained onto the previous)."""
        ids = cls.contextualize_ids(state)
        nodes = [
            ActionNodeBlob(id=nid, family="contextualize", kind=method.kind, config=dict(method.config))
            for nid, method in zip(ids, state.stack, strict=True)
        ]
        chain = [Transition(from_node_id=a, to_node_id=b) for a, b in zip(ids, ids[1:], strict=False)]
        return _Segment(head=ids[0], exits=[ids[-1]], nodes=nodes, transitions=chain)

    @classmethod
    def __bindings(cls, state: PipelineState) -> dict[str, dict]:
        """Thread every stage's data spine — each consumer reads the nearest enabled producer."""
        # 1. The spine anchors — the Binding each downstream slot reads. A stock stage anchors to a
        #    single producer (FromNode); a chain occupying that slot (later phases) supplies its own
        #    convergence Binding here without touching any consumer.
        ir_pre_enrich = cls.__anchor("figures" if state.render_on else "parse", "ir")
        ir_final = cls.__anchor("apply", "ir") if state.enrich_on else ir_pre_enrich
        ctx_ids = cls.contextualize_ids(state)
        chunks_pre_meta = cls.__anchor(ctx_ids[-1] if ctx_ids else "chunk", "chunks")
        chunks_final = cls.__anchor("meta_chunk", "chunks") if state.metachunk_on else chunks_pre_meta

        bindings: dict[str, dict] = {}
        cls.__bind_intake(bindings, state)
        bindings["parse"] = {"source": FromNode(node_id="address", field_name="ingest")}
        if state.render_on:
            bindings["figures"] = {"ingest": FromNode(node_id="address", field_name="ingest"),
                                   "ir": FromNode(node_id="parse", field_name="ir")}
        if state.enrich_on:
            bindings["extract"] = {"ir": ir_pre_enrich}
            bindings["apply"] = {"ir": ir_pre_enrich,
                                 "entries": FromNode(node_id="per_figure", field_name="items")}
        bindings["chunk"] = {"ir": ir_final}
        cls.__bind_stack(bindings, state, ctx_ids)
        if state.metachunk_on:
            bindings["meta_chunk"] = {"chunks": chunks_pre_meta,
                                      "contract": FromRunInput(field_name=_CONTRACT)}
        if state.metadoc_on:
            bindings["meta_doc"] = {"chunks": chunks_final,
                                    "contract": FromRunInput(field_name=_CONTRACT)}
        if state.embed_on:
            bindings["embed"] = {"chunks": chunks_final,
                                 "contract": FromRunInput(field_name=_CONTRACT)}
        bindings["bundle"] = cls.__bundle_bindings(state, ir_final, chunks_final)
        return bindings

    @classmethod
    def __bind_intake(cls, bindings: dict[str, dict], state: PipelineState) -> None:
        """The fixed intake bindings (source/contract from run, probe/pdf from siblings)."""
        bindings["probe"] = {"source": FromRunInput(field_name=_SOURCE)}
        bindings["admit"] = {"source": FromRunInput(field_name=_SOURCE),
                             "probe": FromNode(node_id="probe", field_name="probe"),
                             "contract": FromRunInput(field_name=_CONTRACT)}
        bindings["convert"] = {"source": FromNode(node_id="admit", field_name="source"),
                               "probe": FromNode(node_id="probe", field_name="probe")}
        bindings["pdf_probe"] = {"pdf": FromNode(node_id="convert", field_name="pdf")}
        bindings["address"] = {"source": FromNode(node_id="admit", field_name="source"),
                               "pdf": FromNode(node_id="convert", field_name="pdf"),
                               "probe": FromNode(node_id="pdf_probe", field_name="probe")}

    @classmethod
    def __bind_stack(cls, bindings: dict[str, dict], state: PipelineState, ctx_ids: list[str]) -> None:
        """Chain the contextualize stack onto the chunker and thread doc_meta's source."""
        previous: Binding = cls.__anchor("chunk", "chunks")
        for ctx_id, method in zip(ctx_ids, state.stack, strict=True):
            slots: dict = {"chunks": previous}
            # doc_meta additionally renders the run's declared document metadata.
            if method.kind == "doc_meta":
                slots["source"] = FromRunInput(field_name=_SOURCE)
            bindings[ctx_id] = slots
            previous = cls.__anchor(ctx_id, "chunks")

    @classmethod
    def __bundle_bindings(cls, state: PipelineState, ir_final: Binding, chunks_final: Binding) -> dict:
        """The delivery bindings — optional slots left unbound when their stage is off."""
        slots: dict = {"ingest": FromNode(node_id="address", field_name="ingest"),
                       "ir": ir_final,
                       "chunks": chunks_final}
        if state.render_on:
            slots["pages"] = FromNode(node_id="figures", field_name="pages")
        if state.metadoc_on:
            slots["document_meta"] = FromNode(node_id="meta_doc", field_name="meta")
        if state.embed_on:
            slots["embeddings"] = FromNode(node_id="embed", field_name="embeddings")
        return slots

    @staticmethod
    def __anchor(node_id: str, field_name: str) -> Binding:
        """A single-producer spine anchor — the Binding a downstream slot reads from a stock stage."""
        return FromNode(node_id=node_id, field_name=field_name)


__all__ = ["IngestAssembler"]
