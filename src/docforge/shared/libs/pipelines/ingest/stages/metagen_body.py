# ====== Code Summary ======
# Thin metagen-flavoured shim over the shared ForEachChainBodyBuilder — it holds only the metagen
# knobs (the body id/prefix, the ``request`` loop face, the ``values`` output, and the ``metagen_skip``
# fail-soft terminal) and maps the stage's MetagenOnError onto the optional terminal. The reusable
# "prep → ForEach(chain [+ fail-soft terminal]) → apply" body topology lives in the shared builder; the
# on_error policy stays a GRAPH EDGE, not a node flag: skip_fields → a model-free metagen_skip terminal
# wired OnFailure off the chain's last step (the document survives, only that request's fields drop);
# fail → no terminal, so a final-step failure propagates as a loud ForEach item failure.

# ====== Internal Project Imports ======
from shared_libs.pipelines.build.blob import GroupNodeBlob
from shared_libs.pipelines.build.chain import ChainStepSpec
from shared_libs.pipelines.build.foreach_chain_body import FailSoftTerminal, ForEachChainBodyBuilder
from shared_libs.pipelines.ingest.nodes.metagen.base import MetagenOnError

# ====== Local Project Imports ======
from .state import ChainSpec


class MetagenBodyBuilder:
    """Static builder of a metagen ForEach body from a structgen chain + the on_error policy."""

    BODY_ID = "metagen_path"
    CHAIN_PREFIX = "gen"
    SKIP_ID = "skip"
    GROUP_FIELD = "request"
    OUTPUT_FIELD = "values"

    def __new__(cls, *args: object, **kwargs: object) -> None:
        raise TypeError("MetagenBodyBuilder is a static-only class and cannot be instantiated.")

    @classmethod
    def build(cls, chain: ChainSpec, on_error: MetagenOnError) -> GroupNodeBlob:
        """
        Assemble the per-request body: the structgen chain, plus a fail-soft skip terminal when asked.

        Args:
            chain (ChainSpec): The structgen chain (family ``structgen``, non-scored) whose steps
                each fulfil one GenerationRequest and produce the terminal GeneratedValues.
            on_error (MetagenOnError): skip_fields → append a model-free metagen_skip terminal wired
                OnFailure off the last step; fail → no terminal (a last-step failure fails the item).

        Returns:
            GroupNodeBlob: The ForEach body group (id ``metagen_path``).
        """
        # 1. skip_fields is the only mode that adds the fail-soft terminal; fail leaves it absent.
        terminal = (
            FailSoftTerminal(node_id=cls.SKIP_ID, family="metagen", kind="metagen_skip")
            if on_error == MetagenOnError.SKIP_FIELDS
            else None
        )

        # 2. Delegate the shared body topology, feeding it the metagen-specific face and terminal.
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


__all__ = ["MetagenBodyBuilder"]
