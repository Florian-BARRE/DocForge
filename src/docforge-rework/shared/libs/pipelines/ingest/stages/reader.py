# ====== Code Summary ======
# StateReader — parses an ingestion blob back into a PipelineState (the inverse of the assembler).
# It derives the stage-level truth FROM the graph by family first (so renamed node ids still read):
# which optional stages are present, the selected provider kinds and their configs, the ordered
# contextualize stack, and — the subtle part — the enrich chains, walked out of the per-figure loop
# body (each classifier when_equals branch → its ordered model providers, reading the score_below
# escalation off the edges). What the reader captures, the assembler re-emits verbatim, so a
# view→apply→view round-trip is stable.

# ====== Third-Party Library Imports ======
from loggerplusplus import loggerplusplus

# ====== Internal Project Imports ======
from shared_libs.pipelines.base import ScoreBelow, WhenEquals
from shared_libs.pipelines.build.blob import (
    ActionNodeBlob,
    ForEachNodeBlob,
    GroupNodeBlob,
    NodeBlob,
)
from shared_libs.pipelines.edit.topology import BlobTopology

# ====== Local Project Imports ======
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
        loop = next((n for n in ordered if isinstance(n, ForEachNodeBlob)), None)

        chunker = cls.__by_family(ordered, "chunker")
        embed = cls.__by_family(ordered, "embed")

        state = PipelineState(
            intake_configs=cls.__intake_configs(actions),
            parse_chain=cls.__parse_chain(blob, ordered),
            render_on=cls.__by_family(ordered, "render") is not None,
            render_config=cls.__config_of(cls.__by_family(ordered, "render")),
            enrich_on=loop is not None,
            chunker_kind=chunker.kind if chunker else "structure_aware",
            chunker_config=dict(chunker.config) if chunker else {},
            stack=cls.__stack(ordered),
            metachunk_on=cls.__metagen(ordered, "chunk") is not None,
            metachunk_config=cls.__config_of(cls.__metagen(ordered, "chunk")),
            metadoc_on=cls.__metagen(ordered, "document") is not None,
            metadoc_config=cls.__config_of(cls.__metagen(ordered, "document")),
            embed_on=embed is not None,
            embed_kind=embed.kind if embed else "bge_server",
            embed_config=dict(embed.config) if embed else {},
        )
        # 2. Enrich internals — the classifier config and the per-class chains.
        if loop is not None:
            classify = cls.__body_classify(loop.body)
            if classify is not None:
                state.classify_config = dict(classify.config)
            state.chains = cls.__derive_chains(loop.body)
        return state

    @classmethod
    def __by_family(cls, ordered: list[NodeBlob], family: str) -> ActionNodeBlob | None:
        """The first root action node of a family (families are single-node at root)."""
        return next(
            (n for n in ordered if isinstance(n, ActionNodeBlob) and n.family == family), None
        )

    @classmethod
    def __metagen(cls, ordered: list[NodeBlob], kind: str) -> ActionNodeBlob | None:
        """The metagen node of a given scope kind (chunk / document)."""
        return next(
            (n for n in ordered
             if isinstance(n, ActionNodeBlob) and n.family == "metagen" and n.kind == kind),
            None,
        )

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
        """The ordered contextualize methods (root order = application order)."""
        return [
            StackMethod(kind=node.kind, config=dict(node.config))
            for node in ordered
            if isinstance(node, ActionNodeBlob) and node.family == "contextualize"
        ]

    @classmethod
    def __body_classify(cls, body: GroupNodeBlob) -> ActionNodeBlob | None:
        """The classifier node of the enrich body (the switch driver)."""
        return next(
            (n for n in body.nodes
             if isinstance(n, ActionNodeBlob) and n.kind == "figure_classify"),
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
            steps = cls.__walk_chain(body.transitions, by_id, head, _MODEL_FAMILIES)
            if steps:
                chains[branch.slot] = ChainSpec(family=head.family, steps=steps)
        return chains

    @classmethod
    def __parse_chain(cls, blob: GroupNodeBlob, ordered: list[NodeBlob]) -> ChainSpec:
        """Read the parser stage back as a chain — 1 provider round-trips to a 1-step ChainSpec."""
        parsers = {
            n.id: n for n in ordered if isinstance(n, ActionNodeBlob) and n.family == "parser"
        }
        if not parsers:
            return ChainSpec(family="parser", steps=[ChainStep(kind="docling")])
        head = cls.__chain_head(blob.transitions, parsers, {"parser"})
        return ChainSpec(family="parser", steps=cls.__walk_chain(blob.transitions, parsers, head, {"parser"}))

    @classmethod
    def __chain_head(
        cls, transitions: list, by_id: dict[str, ActionNodeBlob], families: set[str]
    ) -> ActionNodeBlob:
        """The chain's head — the only family node no in-family escalation edge points at."""
        targeted = {
            t.to_node_id for t in transitions
            if t.from_node_id in by_id and t.to_node_id in by_id
            and by_id[t.to_node_id].family in families
        }
        return next((node for nid, node in by_id.items() if nid not in targeted), next(iter(by_id.values())))

    @classmethod
    def __switch_target(cls, body: GroupNodeBlob, classify_id: str, figure_kind: str) -> str | None:
        """The head node a classifier when_equals edge routes a figure class to."""
        for transition in body.transitions:
            if (transition.from_node_id == classify_id
                    and isinstance(transition.condition, WhenEquals)
                    and transition.condition.equals == figure_kind):
                return transition.to_node_id
        return None

    @classmethod
    def __walk_chain(
        cls, transitions: list, by_id: dict[str, ActionNodeBlob], head: ActionNodeBlob,
        families: set[str],
    ) -> list[ChainStep]:
        """Follow a chain's providers, reading the score_below escalation off the edges."""
        steps: list[ChainStep] = []
        current: ActionNodeBlob | None = head
        seen: set[str] = set()
        while current is not None and current.family in families and current.id not in seen:
            seen.add(current.id)
            score_below = cls.__score_below(transitions, current.id, by_id, families)
            steps.append(ChainStep(kind=current.kind, config=dict(current.config),
                                   score_below=score_below))
            current = cls.__next_step(transitions, current.id, by_id, families)
        return steps

    @classmethod
    def __score_below(
        cls, transitions: list, node_id: str, by_id: dict[str, ActionNodeBlob], families: set[str]
    ) -> float | None:
        """The threshold of the ScoreBelow edge escalating this step to the next chain node."""
        for transition in transitions:
            if (transition.from_node_id == node_id
                    and isinstance(transition.condition, ScoreBelow)
                    and transition.to_node_id in by_id
                    and by_id[transition.to_node_id].family in families):
                return transition.condition.threshold
        return None

    @classmethod
    def __next_step(
        cls, transitions: list, node_id: str, by_id: dict[str, ActionNodeBlob], families: set[str]
    ) -> ActionNodeBlob | None:
        """The next chain provider a step escalates to (score_below / on_failure target)."""
        for transition in transitions:
            target = by_id.get(transition.to_node_id)
            if (transition.from_node_id == node_id and target is not None
                    and target.family in families):
                return target
        return None


__all__ = ["StateReader"]
