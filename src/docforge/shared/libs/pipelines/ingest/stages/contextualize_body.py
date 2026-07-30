# ====== Code Summary ======
# Thin contextualize-flavoured shim over the shared ForEachChainBodyBuilder — it holds only the
# contextualize knobs (the body id/prefix, the ``prompt`` loop face, the ``completion`` output, and the
# ``keep_raw`` fail-soft terminal) and maps the stage's OnChunkError onto the optional terminal. The
# reusable "prep → ForEach(chain [+ fail-soft terminal]) → apply" body topology lives in the shared
# builder; the on_error policy stays a GRAPH EDGE, not a node flag: keep_raw → a model-free keep_raw
# terminal wired OnFailure off the chain's last step (the chunk stays raw, the document survives);
# fail → no terminal, so a final-step failure propagates as a loud ForEach item failure.

# ====== Internal Project Imports ======
from shared_libs.pipelines.build.blob import GroupNodeBlob
from shared_libs.pipelines.build.chain import ChainStepSpec
from shared_libs.pipelines.build.foreach_chain_body import FailSoftTerminal, ForEachChainBodyBuilder
from shared_libs.pipelines.ingest.nodes.contextualize.base import OnChunkError

# ====== Local Project Imports ======
from .models import ChainSpec


class ContextualizeBodyBuilder:
    """Static builder of a contextualize ForEach body from a generic-llm chain + the on_error policy."""

    BODY_ID = "ctx_path"
    CHAIN_PREFIX = "ctx"
    KEEP_ID = "keep"
    GROUP_FIELD = "prompt"
    OUTPUT_FIELD = "completion"

    def __new__(cls, *args: object, **kwargs: object) -> None:
        raise TypeError(
            "ContextualizeBodyBuilder is a static-only class and cannot be instantiated."
        )

    @classmethod
    def build(cls, chain: ChainSpec, on_error: OnChunkError) -> GroupNodeBlob:
        """
        Assemble the per-prompt body: the generic-llm chain, plus a fail-soft keep_raw terminal when asked.

        Args:
            chain (ChainSpec): The generic ``llm`` chain (family ``llm``, non-scored) whose steps each
                fulfil the loop's situating prompt and produce the terminal Completion.
            on_error (OnChunkError): keep_raw → append a model-free keep_raw terminal wired OnFailure
                off the last step (the chunk stays raw); fail → no terminal (a last-step failure fails
                the item, so the document fails loudly).

        Returns:
            GroupNodeBlob: The ForEach body group (id ``ctx_path``).
        """
        # 1. keep_raw is the only mode that adds the fail-soft terminal; fail leaves it absent.
        terminal = (
            FailSoftTerminal(node_id=cls.KEEP_ID, family="contextualize", kind="keep_raw")
            if on_error == OnChunkError.KEEP_RAW
            else None
        )

        # 2. Delegate the shared body topology, feeding it the contextualize-specific face and terminal.
        return ForEachChainBodyBuilder.build(
            body_id=cls.BODY_ID,
            chain_prefix=cls.CHAIN_PREFIX,
            family=chain.family,
            steps=[
                ChainStepSpec(
                    kind=step.kind, config=dict(step.config), score_below=step.score_below
                )
                for step in chain.steps
            ],
            group_field=cls.GROUP_FIELD,
            output_field=cls.OUTPUT_FIELD,
            terminal=terminal,
        )


__all__ = ["ContextualizeBodyBuilder"]
