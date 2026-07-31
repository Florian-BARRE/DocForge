# ====== Code Summary ======
# IngestAssembler — turns a PipelineState into a validated-shape ingestion blob. It is the SINGLE
# owner of the pipeline's wiring: it lays the enabled stage SEGMENTS (built by SegmentBuilder) out
# as a linear control-flow chain and threads the DATA SPINES (the IR spine parse→render→enrich, the
# chunks spine chunk→contextualize→metagen) so every consumer always reads the nearest enabled
# producer. Each spine anchor is read straight from the producing segment's ``output`` Binding — a
# plain FromNode for a stock stage, a best-first FromFirst for a chain occupying that slot — so a
# multi-exit provider chain can fill a linear stage slot without any consumer changing. Because the
# assembler recomputes wiring from the enabled set, the compiler can toggle any stage and still emit
# a blob that builds: the "no doubt, coherent end to end" guarantee lives here. default_blob() is
# just assemble(default_state()).

# ====== Third-Party Library Imports ======
from loggerplusplus import loggerplusplus

# ====== Internal Project Imports ======
from shared_libs.pipelines.base import Binding, FromNode, FromRunInput, Transition
from shared_libs.pipelines.build.blob import GroupNodeBlob

# ====== Local Project Imports ======
from .contextualize_stack import ContextualizeStack, StackPosition
from .segments import Segment, SegmentBuilder
from .state import PipelineState

# The run-input field names the entry nodes bind to (kept local to avoid importing the pipeline).
_SOURCE = "source"
_CONTRACT = "contract"


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
        segments = SegmentBuilder.all(state)

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
        bindings = cls.__bindings(state, segments)
        return GroupNodeBlob(
            id="ingest_pipeline", nodes=nodes, transitions=transitions, bindings=bindings
        )

    @classmethod
    def __bindings(cls, state: PipelineState, segments: list[Segment]) -> dict[str, dict]:
        """Thread every stage's data spine — each consumer reads the nearest enabled producer."""
        # 1. The spine anchors — read straight from each stage segment's own ``output`` Binding, so a
        #    stock stage (FromNode) and a chain occupying that slot (a best-first FromFirst) rebind
        #    every downstream consumer identically, and exits can never drift from the convergence.
        by_key = {segment.key: segment for segment in segments}
        ir_pre_enrich = (by_key.get("render") or by_key["parse"]).output
        ir_final = by_key["enrich"].output if "enrich" in by_key else ir_pre_enrich
        positions = ContextualizeStack.positions(state)
        chunks_pre_meta = (by_key.get("contextualize") or by_key["chunk"]).output
        chunks_final = (
            by_key["metagen_chunk"].output if "metagen_chunk" in by_key else chunks_pre_meta
        )

        bindings: dict[str, dict] = {}
        # Each stage segment carries its own internal node bindings (a chain's per-step face); the
        # spine/cross-stage bindings below thread the rest.
        for segment in segments:
            bindings.update(segment.bindings)
        cls.__bind_intake(bindings, state)
        if state.render_on:
            bindings["figures"] = {
                "ingest": FromNode(node_id="address", field_name="ingest"),
                "ir": by_key["parse"].output,
            }
        if state.enrich_on:
            bindings["extract"] = {"ir": ir_pre_enrich}
            bindings["apply"] = {
                "ir": ir_pre_enrich,
                "entries": FromNode(node_id="per_figure", field_name="items"),
            }
        bindings["chunk"] = {"ir": ir_final}
        cls.__bind_stack(bindings, positions, by_key["chunk"].output, ir_final)
        if state.metachunk_on:
            # prep reads the pre-meta chunks + contract; apply merges the loop's values back onto
            # those same pre-meta chunks. chunks_final then reads apply's output.
            bindings["meta_chunk_prep"] = {
                "chunks": chunks_pre_meta,
                "contract": FromRunInput(field_name=_CONTRACT),
            }
            bindings["meta_chunk_apply"] = {
                "chunks": chunks_pre_meta,
                "values": FromNode(node_id="meta_chunk_loop", field_name="items"),
            }
        if state.metadoc_on:
            # prep builds the document view from the fully-annotated chunks; apply joins the loop's
            # values into one document meta (it needs only the values, not the chunks).
            bindings["meta_doc_prep"] = {
                "chunks": chunks_final,
                "contract": FromRunInput(field_name=_CONTRACT),
            }
            bindings["meta_doc_apply"] = {
                "values": FromNode(node_id="meta_doc_loop", field_name="items"),
            }
        if state.embed_on:
            # Embed may be a chain: every step consumes the SAME face (chunks spine + contract), so
            # bind it onto each step id (a single embedder's only exit is 'embed' — byte-identical).
            embed_face = {"chunks": chunks_final, "contract": FromRunInput(field_name=_CONTRACT)}
            for step_id in by_key["embed"].exits:
                bindings[step_id] = dict(embed_face)
        embed_output = by_key["embed"].output if state.embed_on else None
        bindings["bundle"] = cls.__bundle_bindings(state, ir_final, chunks_final, embed_output)
        return bindings

    @classmethod
    def __bind_intake(cls, bindings: dict[str, dict], state: PipelineState) -> None:
        """The fixed intake bindings (source/contract from run, probe/pdf from siblings)."""
        bindings["probe"] = {"source": FromRunInput(field_name=_SOURCE)}
        bindings["admit"] = {
            "source": FromRunInput(field_name=_SOURCE),
            "probe": FromNode(node_id="probe", field_name="probe"),
            "contract": FromRunInput(field_name=_CONTRACT),
        }
        bindings["convert"] = {
            "source": FromNode(node_id="admit", field_name="source"),
            "probe": FromNode(node_id="probe", field_name="probe"),
        }
        bindings["pdf_probe"] = {"pdf": FromNode(node_id="convert", field_name="pdf")}
        bindings["address"] = {
            "source": FromNode(node_id="admit", field_name="source"),
            "source_probe": FromNode(node_id="probe", field_name="probe"),
            "pdf": FromNode(node_id="convert", field_name="pdf"),
            "probe": FromNode(node_id="pdf_probe", field_name="probe"),
        }

    @classmethod
    def __bind_stack(
        cls,
        bindings: dict[str, dict],
        positions: list[StackPosition],
        chunk_output: Binding,
        ir: Binding,
    ) -> None:
        """Chain the contextualize stack onto the chunker, thread doc_meta's source/ir and the llm apply.

        Each slot's ``head`` reads the previous slot's chunks; the next slot then reads THIS slot's
        ``output``. For an llm slot the apply additionally merges the loop's completions back onto the
        SAME incoming chunks its prep read (like metagen's apply binds the pre-meta chunks) — the join
        is positional, so the incoming chunks and the loop's items line up one-to-one.
        """
        previous: Binding = chunk_output
        for position in positions:
            slots: dict = {"chunks": previous}
            # doc_meta additionally renders the run's declared document metadata, and reads the IR
            # for the true first-heading fallback (a coalesced chunk's heading_path may have lost it).
            if position.method.kind == "doc_meta":
                slots["source"] = FromRunInput(field_name=_SOURCE)
                slots["ir"] = ir
            bindings[position.head_id] = slots
            if position.is_llm:
                bindings[position.apply_id] = {
                    "chunks": previous,
                    "completions": FromNode(node_id=position.loop_id, field_name="items"),
                }
            previous = position.output

    @classmethod
    def __bundle_bindings(
        cls,
        state: PipelineState,
        ir_final: Binding,
        chunks_final: Binding,
        embed_output: Binding | None,
    ) -> dict:
        """The delivery bindings — optional slots left unbound when their stage is off."""
        slots: dict = {
            "ingest": FromNode(node_id="address", field_name="ingest"),
            "ir": ir_final,
            "chunks": chunks_final,
        }
        if state.render_on:
            slots["pages"] = FromNode(node_id="figures", field_name="pages")
        if state.metadoc_on:
            slots["document_meta"] = FromNode(node_id="meta_doc_apply", field_name="meta")
        # The embed anchor is the stage's convergence — FromNode for one embedder, FromFirst a chain.
        if state.embed_on and embed_output is not None:
            slots["embeddings"] = embed_output
        return slots


__all__ = ["IngestAssembler"]
