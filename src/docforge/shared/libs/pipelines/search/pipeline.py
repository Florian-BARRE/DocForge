# ====== Code Summary ======
# SearchPipeline — the class that TIES the search pipeline together: it declares which node families
# compose it, triggers their registration, is the origin of the palette the UI is populated from,
# and carries the default topology (the minimal P1 graph: normalize → encode → retrieve(hybrid) →
# hydrate → deliver(hits)). It is the search analog of IngestPipeline: same engine, same builder,
# same validator — only the families, run inputs and default blob differ.

# ====== Internal Project Imports ======
import shared_libs.pipelines.search.nodes  # noqa: F401 — registers the search node families
from shared_libs.pipelines.base import FromNode, FromRunInput, IoSlot, Transition
from shared_libs.pipelines.build import ActionNodeBlob, GroupNodeBlob
from shared_libs.pipelines.introspection import (
    ArtefactCatalog,
    FamilyCatalog,
    GraphMechanics,
    Palette,
    PipelinePreset,
)
from shared_libs.pipelines.registry import NodeRegistry
from shared_libs.pipelines.validation import PaletteScopeValidator


class SearchPipeline:
    """Static entry point of the search pipeline — its families, its palette, its topology."""

    # The families a search pipeline is assembled from, in stage order; deliver is the reused
    # capability family shared with ingestion (its ``hits`` kind).
    FAMILIES = (
        "query",
        "encode",
        "retrieve",
        "fuse",
        "rerank",
        "postprocess",
        "deliver",
    )

    # Per-family kind allowlist for SHARED families: ``deliver`` is reused by ingestion, so its
    # palette view must be scoped to search's own terminal kind (``hits``) — otherwise ingestion's
    # ``bundle`` would leak into the search palette. Exclusive families stay unrestricted.
    FAMILY_KINDS: dict[str, set[str]] = {"deliver": {"hits"}}

    # The artefacts the RUN hands to the graph — the sources a FromRunInput binding can target.
    RUN_INPUTS = (
        IoSlot(
            name="query",
            artefact_type="RawQuery",
            description="The caller's raw query: text, requested top_k and retrieval flags.",
        ),
        IoSlot(
            name="filters",
            artefact_type="QueryFilters",
            description="The caller's raw field → value filter map applied to the retrieval.",
        ),
        IoSlot(
            name="contract",
            artefact_type="SearchContract",
            description=(
                "The collection's search contract: its identity, its own embedder (kind + config) "
                "and its filterable field names."
            ),
        ),
    )

    def __new__(cls, *args: object, **kwargs: object) -> None:
        raise TypeError("SearchPipeline is a static-only class and cannot be instantiated.")

    @classmethod
    def palette(cls, full: bool = False) -> Palette:
        """
        The UI palette of the search pipeline — every block available to assemble it.

        Mirrors IngestPipeline.palette: the default palette carries only the families (each node
        with its full describe() card); the FULL palette adds the graph-level vocabulary (run
        inputs, mechanics, artefacts) for the advanced, headless design surface.

        Args:
            full (bool): When True, also fill run_inputs, mechanics and artefacts.

        Returns:
            Palette: One FamilyCatalog per family; the advanced blocks when ``full``.
        """
        # 1. The families every consumer needs (node cards: labels, config schema, I/O). A shared
        #    family is scoped to this pipeline kind's own kinds via the FAMILY_KINDS allowlist.
        families = [
            FamilyCatalog.from_family(family, cls.FAMILY_KINDS.get(family))
            for family in cls.FAMILIES
            if family in NodeRegistry.families()
        ]
        if not full:
            return Palette(families=families)

        # 2. The advanced blocks — the graph-editing vocabulary, described on demand only. No
        #    stage-action union is passed: search has no stage rail, so mechanics.stage_actions
        #    stays empty (edit_operations still surface — graph edits are pipeline-agnostic).
        return Palette(
            families=families,
            run_inputs=list(cls.RUN_INPUTS),
            mechanics=GraphMechanics.describe(),
            artefacts=ArtefactCatalog.describe(),
        )

    @classmethod
    def allowed_kinds(cls) -> dict[str, set[str]]:
        """
        The (family → kinds) map a valid built search graph may use — the palette scope.

        Resolved from ``FAMILIES`` (the families search is built from) and ``FAMILY_KINDS`` (the
        per-family scoping for the shared ``deliver`` family → ``hits``). Admits the future
        ``SELECTABLE=False`` placeholder kinds registered under search families, so a valid graph is
        never rejected for a legitimately registered kind. Fed to ``PaletteScopeValidator`` at the
        write boundary.

        Returns:
            dict[str, set[str]]: Family → the set of kinds a search graph may contain.
        """
        return PaletteScopeValidator.resolve(cls.FAMILIES, cls.FAMILY_KINDS)

    @classmethod
    def default_blob(cls) -> GroupNodeBlob:
        """
        The stock search pipeline — the blob a new collection's search editor opens on.

        The minimal P1 graph: normalize the query → encode it with the collection's embedder →
        retrieve a hybrid candidate pool → hydrate + rank the hits → deliver the SearchResult. A
        single linear OnSuccess chain; the fuse/rerank/post-process stages join as later phases.

        Returns:
            GroupNodeBlob: The serialised default topology (nodes, transitions, bindings).
        """
        # 1. The five nodes of the smallest viable search graph (empty config = every default).
        nodes = [
            ActionNodeBlob(id="normalize", family="query", kind="normalize"),
            ActionNodeBlob(id="encode", family="encode", kind="collection"),
            ActionNodeBlob(id="retrieve", family="retrieve", kind="hybrid"),
            ActionNodeBlob(id="hydrate", family="postprocess", kind="hydrate"),
            ActionNodeBlob(id="deliver", family="deliver", kind="hits"),
        ]

        # 2. The linear control flow (OnSuccess is the Transition default).
        transitions = [
            Transition(from_node_id="normalize", to_node_id="encode"),
            Transition(from_node_id="encode", to_node_id="retrieve"),
            Transition(from_node_id="retrieve", to_node_id="hydrate"),
            Transition(from_node_id="hydrate", to_node_id="deliver"),
        ]

        # 3. The data wiring — run inputs at the edges, node-to-node along the spine.
        bindings = {
            "normalize": {
                "query": FromRunInput(field_name="query"),
                "filters": FromRunInput(field_name="filters"),
            },
            "encode": {
                "spec": FromNode(node_id="normalize", field_name="spec"),
                "contract": FromRunInput(field_name="contract"),
            },
            "retrieve": {
                "spec": FromNode(node_id="normalize", field_name="spec"),
                "encoded": FromNode(node_id="encode", field_name="encoded"),
            },
            "hydrate": {
                "candidates": FromNode(node_id="retrieve", field_name="candidates"),
                "spec": FromNode(node_id="normalize", field_name="spec"),
            },
            "deliver": {
                "ranked": FromNode(node_id="hydrate", field_name="ranked"),
                "query": FromRunInput(field_name="query"),
            },
        }
        return GroupNodeBlob(
            id="search_pipeline", nodes=nodes, transitions=transitions, bindings=bindings
        )

    @classmethod
    def rerank_blob(cls) -> GroupNodeBlob:
        """
        The fusion + cross-encoder rerank search topology — the canonical "rerank on" blob.

        The stock ``default_blob`` fusion chain with ONE node inserted between retrieve and hydrate:
        normalize → encode → retrieve → RERANK → hydrate → deliver. The rerank node re-scores the
        fused pool's top candidates with the in-stack cross-encoder and emits a plain CandidateSet,
        so the hydrate node still does the ranking + top_k cut, its Consumes unchanged. This is the
        blob the UI's rerank toggle stores; the reranker config stays in the blob (the user never
        edits it). A single linear OnSuccess chain — no tuning.

        Returns:
            GroupNodeBlob: The serialised fusion + rerank topology (nodes, transitions, bindings).
        """
        # 1. The fusion chain's nodes plus the cross-encoder rerank node (empty config = defaults).
        nodes = [
            ActionNodeBlob(id="normalize", family="query", kind="normalize"),
            ActionNodeBlob(id="encode", family="encode", kind="collection"),
            ActionNodeBlob(id="retrieve", family="retrieve", kind="hybrid"),
            ActionNodeBlob(id="rerank", family="rerank", kind="cross_encoder"),
            ActionNodeBlob(id="hydrate", family="postprocess", kind="hydrate"),
            ActionNodeBlob(id="deliver", family="deliver", kind="hits"),
        ]

        # 2. The linear control flow — rerank slots in between retrieve and hydrate.
        transitions = [
            Transition(from_node_id="normalize", to_node_id="encode"),
            Transition(from_node_id="encode", to_node_id="retrieve"),
            Transition(from_node_id="retrieve", to_node_id="rerank"),
            Transition(from_node_id="rerank", to_node_id="hydrate"),
            Transition(from_node_id="hydrate", to_node_id="deliver"),
        ]

        # 3. The data wiring — rerank reads the fused pool from retrieve + the query text from
        #    normalize; hydrate's candidates are rebound onto rerank's re-scored output.
        bindings = {
            "normalize": {
                "query": FromRunInput(field_name="query"),
                "filters": FromRunInput(field_name="filters"),
            },
            "encode": {
                "spec": FromNode(node_id="normalize", field_name="spec"),
                "contract": FromRunInput(field_name="contract"),
            },
            "retrieve": {
                "spec": FromNode(node_id="normalize", field_name="spec"),
                "encoded": FromNode(node_id="encode", field_name="encoded"),
            },
            "rerank": {
                "candidates": FromNode(node_id="retrieve", field_name="candidates"),
                "spec": FromNode(node_id="normalize", field_name="spec"),
            },
            "hydrate": {
                "candidates": FromNode(node_id="rerank", field_name="candidates"),
                "spec": FromNode(node_id="normalize", field_name="spec"),
            },
            "deliver": {
                "ranked": FromNode(node_id="hydrate", field_name="ranked"),
                "query": FromRunInput(field_name="query"),
            },
        }
        return GroupNodeBlob(
            id="search_pipeline", nodes=nodes, transitions=transitions, bindings=bindings
        )

    @classmethod
    def _query_transform_blob(cls, family: str, kind: str) -> GroupNodeBlob:
        """
        The stock chain with ONE query-transform node spliced between normalize and encode.

        Shared spine of ``rewrite_blob`` and ``hyde_blob`` (they differ only in the node kind): a
        QuerySpec→QuerySpec transform sits at ``qnode`` (normalize → QNODE → encode → …). The splice
        is the one extra step vs rerank — the normalised spec has THREE downstream consumers
        (encode, retrieve, hydrate), so all three are repointed onto the transform's output; the
        transform itself reads the spec from normalize. The node is provider-hosted and OFF by
        default (never in ``default_blob``); its empty config carries the endpoint defaults until the
        user sets real per-collection values. It degrades to the original query on any failure.

        Args:
            family (str): The transform node's family (``query``).
            kind (str): The transform node's kind (``rewrite`` or ``hyde``).

        Returns:
            GroupNodeBlob: The serialised topology with the query transform spliced in.
        """
        qnode = kind
        # 1. The default nodes plus the query-transform node (empty config = endpoint defaults).
        nodes = [
            ActionNodeBlob(id="normalize", family="query", kind="normalize"),
            ActionNodeBlob(id=qnode, family=family, kind=kind),
            ActionNodeBlob(id="encode", family="encode", kind="collection"),
            ActionNodeBlob(id="retrieve", family="retrieve", kind="hybrid"),
            ActionNodeBlob(id="hydrate", family="postprocess", kind="hydrate"),
            ActionNodeBlob(id="deliver", family="deliver", kind="hits"),
        ]

        # 2. The linear control flow — the transform slots in between normalize and encode.
        transitions = [
            Transition(from_node_id="normalize", to_node_id=qnode),
            Transition(from_node_id=qnode, to_node_id="encode"),
            Transition(from_node_id="encode", to_node_id="retrieve"),
            Transition(from_node_id="retrieve", to_node_id="hydrate"),
            Transition(from_node_id="hydrate", to_node_id="deliver"),
        ]

        # 3. The data wiring — the transform reads normalize.spec; EVERY former normalize.spec
        #    consumer (encode, retrieve, hydrate) is repointed onto the transform's output spec.
        bindings = {
            "normalize": {
                "query": FromRunInput(field_name="query"),
                "filters": FromRunInput(field_name="filters"),
            },
            qnode: {"spec": FromNode(node_id="normalize", field_name="spec")},
            "encode": {
                "spec": FromNode(node_id=qnode, field_name="spec"),
                "contract": FromRunInput(field_name="contract"),
            },
            "retrieve": {
                "spec": FromNode(node_id=qnode, field_name="spec"),
                "encoded": FromNode(node_id="encode", field_name="encoded"),
            },
            "hydrate": {
                "candidates": FromNode(node_id="retrieve", field_name="candidates"),
                "spec": FromNode(node_id=qnode, field_name="spec"),
            },
            "deliver": {
                "ranked": FromNode(node_id="hydrate", field_name="ranked"),
                "query": FromRunInput(field_name="query"),
            },
        }
        return GroupNodeBlob(
            id="search_pipeline", nodes=nodes, transitions=transitions, bindings=bindings
        )

    @classmethod
    def rewrite_blob(cls) -> GroupNodeBlob:
        """
        The stock chain with the LLM query-rewrite node spliced in — the canonical "rewrite on" blob.

        normalize → REWRITE → encode → retrieve → hydrate → deliver. The rewrite node replaces the
        spec's text with an LLM-strengthened query; encode/retrieve/hydrate all read the rewritten
        spec. This is the blob the UI's rewrite toggle stores; the provider config lives in the
        blob (set per collection). It degrades to the original query on any provider failure.

        Returns:
            GroupNodeBlob: The serialised rewrite topology (nodes, transitions, bindings).
        """
        return cls._query_transform_blob("query", "rewrite")

    @classmethod
    def hyde_blob(cls) -> GroupNodeBlob:
        """
        The stock chain with the HyDE node spliced in — the canonical "HyDE on" blob.

        normalize → HYDE → encode → retrieve → hydrate → deliver. The HyDE node appends a
        hypothetical answer passage to the spec's text so encode embeds the richer text;
        retrieve/hydrate read the enriched spec. This is the blob the UI's HyDE toggle stores; the
        provider config lives in the blob (set per collection). It degrades to the original query on
        any provider failure.

        Returns:
            GroupNodeBlob: The serialised HyDE topology (nodes, transitions, bindings).
        """
        return cls._query_transform_blob("query", "hyde")

    @classmethod
    def dense_only_blob(cls) -> GroupNodeBlob:
        """
        The DENSE-ONLY search topology — pure semantic retrieval, no lexical axis.

        The stock ``default_blob`` with the normalize node configured to default a target-less query
        to the dense (semantic) content vector only — the sparse BM25 axis is never queried for a
        plain query. Same linear spine (normalize → encode → retrieve → hydrate → deliver); the only
        difference is ``normalize.content_modalities = "semantic"``. Pick it for a dense-only
        embedder or a pure-meaning retrieval profile; an explicit per-query targets list still wins.

        Returns:
            GroupNodeBlob: The serialised dense-only topology (nodes, transitions, bindings).
        """
        # 1. Start from the stock blob and narrow the normalize node's default content modalities.
        blob = cls.default_blob()
        for node in blob.nodes:
            if node.id == "normalize":
                node.config = {**dict(node.config or {}), "content_modalities": "semantic"}
        return blob

    # The creation presets this pipeline offers for the collection's SEARCH blob — each a curated,
    # validation-passing stock topology (a starting point, NOT a new engine). The first entry is the
    # default. Provider-hosted query transforms (rewrite/HyDE) stay OFF in every preset.
    _PRESETS: tuple[tuple[str, str, str, bool], ...] = (
        (
            "hybrid",
            "Hybrid (dense + sparse)",
            "The stock search: fuse the dense (semantic) and sparse (lexical) content vectors with "
            "RRF for the most robust recall. The balanced default for most collections.",
            True,
        ),
        (
            "hybrid_rerank",
            "Hybrid + rerank",
            "Hybrid retrieval followed by a cross-encoder rerank of the top candidates (in-stack "
            "reranker) for higher precision at the top of the list. Costs an extra rerank pass per "
            "query.",
            False,
        ),
        (
            "dense_only",
            "Dense only (semantic)",
            "Pure semantic retrieval on the dense vector — the sparse BM25 axis is never queried for "
            "a plain query. Pick it for a dense-only embedder or a pure-meaning profile.",
            False,
        ),
    )

    # name -> the builder method that assembles its stock blob (resolved server-side, not UI-sent).
    _PRESET_BLOBS: dict[str, str] = {
        "hybrid": "default_blob",
        "hybrid_rerank": "rerank_blob",
        "dense_only": "dense_only_blob",
    }

    @classmethod
    def presets(cls) -> list[PipelinePreset]:
        """
        The discoverable creation presets of the search pipeline (name + label + rationale).

        Carries only the metadata a schema-driven UI / the MCP needs to OFFER the choice — the blob
        each selects is resolved server-side by ``preset_blob``. The default preset is flagged.

        Returns:
            list[PipelinePreset]: One entry per offered preset, in display order.
        """
        return [
            PipelinePreset(name=name, label=label, description=description, is_default=is_default)
            for name, label, description, is_default in cls._PRESETS
        ]

    @classmethod
    def preset_blob(cls, preset: str | None) -> GroupNodeBlob:
        """
        The stock search blob a creation preset selects.

        An unknown or omitted preset falls back to the default (``hybrid``, == ``default_blob``).

        Args:
            preset (str | None): The preset name, or None for the default.

        Returns:
            GroupNodeBlob: The selected stock search topology.
        """
        method_name = cls._PRESET_BLOBS.get(preset or "hybrid", "default_blob")
        return getattr(cls, method_name)()


__all__ = ["SearchPipeline"]
