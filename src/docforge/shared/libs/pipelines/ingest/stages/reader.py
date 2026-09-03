# ====== Code Summary ======
# StateReader — parses an ingestion blob back into a PipelineState (the inverse of the assembler).
# It derives the stage-level truth FROM the graph by family first (so renamed node ids still read):
# which optional stages are present, the selected provider kinds and their configs, the ordered
# contextualize stack, and — the subtle part — the loops. There are now THREE ForEach loops (enrich +
# the two metagen scopes), so the enrich loop is told apart by its BODY (only it carries a
# figure_classify), and each metagen ladder is read via MetagenReader (its prep + structgen chain).
# The generic chain walk is delegated to ChainWalker. What the reader captures, the assembler re-emits
# verbatim, so a view→apply→view round-trip is stable.

# ====== Third-Party Library Imports ======
from loggerplusplus import loggerplusplus

# ====== Internal Project Imports ======
from shared_libs.pipelines.base import WhenEquals
from shared_libs.pipelines.build.blob import (
    ActionNodeBlob,
    ForEachNodeBlob,
    GroupNodeBlob,
    NodeBlob,
)
from shared_libs.pipelines.edit.topology import BlobTopology

# ====== Local Project Imports ======
from .chain_walk import ChainWalker
from .contextualize_read import ContextualizeReader
from .metagen_read import MetagenReader
from .models import ChainStep, StackMethod
from .spec import StageSpecs
from .state import ChainSpec, PipelineState

_MODEL_FAMILIES = {"ocr", "vlm", "llm"}


class StateReader:
    """Static reader that derives a PipelineState from an ingestion blob."""

    logger = loggerplusplus.bind(identifier="StateReader")

    def __new__(cls, *args: object, **kwargs: object) -> None:
        raise TypeError("StateReader is a static-only class and cannot be instantiated.")

    @classmethod
    def read(cls, blob: GroupNodeBlob) -> PipelineState:
        """
        Derive the canonical PipelineState from a blob.

        Args:
            blob (GroupNodeBlob): The ingestion blob to read.

        Returns:
            PipelineState: The stage-level state the view and compiler operate on.
        """
        ordered = BlobTopology.ordered_nodes(blob)
        actions = {node.id: node for node in ordered if isinstance(node, ActionNodeBlob)}
        enrich_loop = cls.__enrich_loop(ordered)
        chunk_prep = MetagenReader.prep(ordered, "chunk_prep")
        doc_prep = MetagenReader.prep(ordered, "document_prep")

        chunker = cls.__by_family(ordered, "chunker")

        state = PipelineState(
            intake_configs=cls.__intake_configs(actions),
            parse_chain=cls.__linear_chain(blob, ordered, "parser", "docling"),
            render_on=cls.__by_family(ordered, "render") is not None,
            render_config=cls.__config_of(cls.__by_family(ordered, "render")),
            enrich_on=enrich_loop is not None,
            chunker_kind=chunker.kind if chunker else "structure_aware",
            chunker_config=dict(chunker.config) if chunker else {},
            stack=cls.__stack(ordered),
            metachunk_on=chunk_prep is not None,
            metachunk_config=cls.__config_of(chunk_prep),
            metachunk_chain=MetagenReader.chain(ordered, chunk_prep),
            metadoc_on=doc_prep is not None,
            metadoc_config=cls.__config_of(doc_prep),
            metadoc_chain=MetagenReader.chain(ordered, doc_prep),
            embed_on=cls.__by_family(ordered, "embed") is not None,
            embed_chain=cls.__linear_chain(blob, ordered, "embed", "bge_server"),
        )
        # Enrich internals — the mode, the classifier config, the chains and the loop concurrency
        # (read straight off the ForEach, so a blob omitting it round-trips to the stock 4). The mode
        # is DERIVED from topology: a body with a classifier is classified, one without is ocr_only.
        if enrich_loop is not None:
            classify = cls.__body_classify(enrich_loop.body)
            if classify is not None:
                state.figure_enrich_mode = "classified"
                state.classify_config = dict(classify.config)
                state.chains = cls.__derive_chains(enrich_loop.body)
            else:
                state.figure_enrich_mode = "ocr_only"
                state.chains = cls.__derive_ocr_only_chain(enrich_loop.body)
            state.figure_concurrency = enrich_loop.max_concurrency
        return state

    @classmethod
    def __by_family(cls, ordered: list[NodeBlob], family: str) -> ActionNodeBlob | None:
        """The first root action node of a family (families are single-node at root)."""
        return next(
            (n for n in ordered if isinstance(n, ActionNodeBlob) and n.family == family), None
        )

    @classmethod
    def __enrich_loop(cls, ordered: list[NodeBlob]) -> ForEachNodeBlob | None:
        """The enrich per-figure loop — the only ForEach whose body carries ``enrich``-family nodes.

        Three+ ForEach loops share the root (enrich + the two metagen scopes + any contextualize llm
        loop). Detecting by the ``enrich`` family (figure_entry is always present, in both classified
        AND ocr_only bodies) is what tells the enrich loop apart even when there is no classifier —
        metagen/contextualize bodies never carry an enrich-family node.
        """
        return next(
            (n for n in ordered if isinstance(n, ForEachNodeBlob) and cls.__is_enrich_body(n.body)),
            None,
        )

    @staticmethod
    def __is_enrich_body(body: GroupNodeBlob) -> bool:
        """Whether a ForEach body is the enrich loop's (carries at least one enrich-family node)."""
        return any(isinstance(n, ActionNodeBlob) and n.family == "enrich" for n in body.nodes)

    @staticmethod
    def __config_of(node: ActionNodeBlob | None) -> dict:
        """The config of a node, or an empty dict when absent."""
        return dict(node.config) if node is not None else {}

    @classmethod
    def __intake_configs(cls, actions: dict[str, ActionNodeBlob]) -> dict[str, dict]:
        """Capture the fixed intake nodes' configs (only the ones actually carrying config)."""
        captured: dict[str, dict] = {}
        for node_id in ("probe", "admit", "convert", "pdf_probe", "address"):
            node = actions.get(node_id)
            if node is not None and node.config:
                captured[node_id] = dict(node.config)
        return captured

    @classmethod
    def __stack(cls, ordered: list[NodeBlob]) -> list[StackMethod]:
        """The ordered contextualize methods (root order = application order).

        Delegated to ContextualizeReader: a simple method is one node, while the llm method is the
        externalised prep → ForEach(llm chain [+ keep_raw]) → apply topology whose chain is walked
        out of the loop body and whose apply is skipped.
        """
        return ContextualizeReader.stack(ordered)

    @classmethod
    def __body_classify(cls, body: GroupNodeBlob) -> ActionNodeBlob | None:
        """The classifier node of the enrich body (the switch driver)."""
        return next(
            (
                n
                for n in body.nodes
                if isinstance(n, ActionNodeBlob) and n.kind == "figure_classify"
            ),
            None,
        )

    @classmethod
    def __derive_chains(cls, body: GroupNodeBlob) -> dict[str, ChainSpec]:
        """Walk each figure-class branch out of the body into a chain spec."""
        classify = cls.__body_classify(body)
        if classify is None:
            return {}
        by_id = {n.id: n for n in body.nodes if isinstance(n, ActionNodeBlob)}
        chains: dict[str, ChainSpec] = {}
        for branch in StageSpecs.FIGURE_BRANCHES:
            head_id = cls.__switch_target(body, classify.id, branch.figure_kind)
            head = by_id.get(head_id) if head_id else None
            if head is None or head.family not in _MODEL_FAMILIES:
                continue
            steps = ChainWalker.walk(body.transitions, by_id, head, _MODEL_FAMILIES)
            if steps:
                chains[branch.slot] = ChainSpec(family=head.family, steps=steps)
        return chains

    @classmethod
    def __derive_ocr_only_chain(cls, body: GroupNodeBlob) -> dict[str, ChainSpec]:
        """Walk the single OCR chain out of an ocr_only body into the scanned_text_ocr slot."""
        by_id = {n.id: n for n in body.nodes if isinstance(n, ActionNodeBlob) and n.family == "ocr"}
        if not by_id:
            return {}
        head = ChainWalker.head(body.transitions, by_id, {"ocr"})
        steps = ChainWalker.walk(body.transitions, by_id, head, {"ocr"})
        return {"scanned_text_ocr": ChainSpec(family="ocr", steps=steps)} if steps else {}

    @classmethod
    def __linear_chain(
        cls, blob: GroupNodeBlob, ordered: list[NodeBlob], family: str, default_kind: str
    ) -> ChainSpec:
        """Read a chain-capable linear stage back as a chain (parse / embed).

        A single provider round-trips to a 1-step ChainSpec; a missing stage yields the stock 1-step
        default so a re-enable starts from a valid provider.

        Args:
            blob (GroupNodeBlob): The blob whose top-level transitions carry the escalation edges.
            ordered (list[NodeBlob]): The topologically ordered nodes.
            family (str): The registry family whose nodes form the chain (``parser`` / ``embed``).
            default_kind (str): The stock kind used when the stage is absent from the blob.

        Returns:
            ChainSpec: The stage's chain (family + ordered steps with their score thresholds).
        """
        nodes = {n.id: n for n in ordered if isinstance(n, ActionNodeBlob) and n.family == family}
        if not nodes:
            return ChainSpec(family=family, steps=[ChainStep(kind=default_kind)])
        head = ChainWalker.head(blob.transitions, nodes, {family})
        return ChainSpec(
            family=family, steps=ChainWalker.walk(blob.transitions, nodes, head, {family})
        )

    @classmethod
    def __switch_target(cls, body: GroupNodeBlob, classify_id: str, figure_kind: str) -> str | None:
        """The head node a classifier when_equals edge routes a figure class to."""
        for transition in body.transitions:
            if (
                transition.from_node_id == classify_id
                and isinstance(transition.condition, WhenEquals)
                and transition.condition.equals == figure_kind
            ):
                return transition.to_node_id
        return None


__all__ = ["StateReader"]
