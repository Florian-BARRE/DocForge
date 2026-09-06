# ====== Code Summary ======
# EstimateOverrideMerger — folds a collection's PARTIAL EstimateOverrides over the estimator's global
# defaults, producing the concrete RateTable + EstimateAssumptions the pure estimator consumes. The
# merge is partial and non-destructive: an absent override subtree falls through to the default, a
# provided one overrides only its own keys (each rate map is copy-then-update, never replaced). The
# collection's ACTUAL chunker config is layered LAST for chunk sizing, so the pipeline stays
# authoritative for target_chunk_tokens / chunk_overlap_ratio even when an override also names them.

# ====== Third-Party Library Imports ======
from loggerplusplus import loggerplusplus

# ====== Internal Project Imports ======
from shared_libs.pipelines.ingest.estimate import EstimateAssumptions, RateTable

# ====== Local Project Imports ======
from .overrides import EstimateOverrides


class EstimateOverrideMerger:
    """Static helper: merge a collection's partial estimate overrides over the global defaults."""

    logger = loggerplusplus.bind(identifier="EstimateOverrideMerger")

    def __new__(cls, *args: object, **kwargs: object) -> None:
        raise TypeError("EstimateOverrideMerger is a static-only class and cannot be instantiated.")

    @classmethod
    def merged_rates(cls, overrides: EstimateOverrides | None) -> RateTable:
        """
        Build the effective rate table: the canonical defaults with the override's maps merged in.

        Args:
            overrides (EstimateOverrides | None): The collection's partial overrides (or None).

        Returns:
            RateTable: The defaults when no rate override is present, else a per-key merge.
        """
        # Delegate to the ONE canonical fold in shared (RateTable.from_overrides) so the estimator here
        # and the worker meter price from byte-identical rate tables — the "priced from identical
        # numbers" contract. Dump the validated model to the stored JSONB shape the fold consumes.
        raw = overrides.model_dump(mode="json") if overrides is not None else None
        return RateTable.from_overrides(raw)

    @classmethod
    def merged_assumptions(
        cls, overrides: EstimateOverrides | None, chunker_config: dict
    ) -> EstimateAssumptions:
        """
        Build the effective assumptions: defaults ← partial override ← the ACTUAL chunker config.

        Args:
            overrides (EstimateOverrides | None): The collection's partial overrides (or None).
            chunker_config (dict): The collection's chunker node config (authoritative for sizing).

        Returns:
            EstimateAssumptions: The merged assumptions, with chunk sizing taken from the pipeline.
        """
        # 1. Defaults, then overlay only the assumption keys the override actually provided.
        base = EstimateAssumptions()
        if overrides is not None and overrides.assumptions is not None:
            provided = overrides.assumptions.model_dump(exclude_none=True)
            base = base.model_copy(update=provided)

        # 2. The pipeline's chunker config wins on top for chunk sizing (falls back to the merged
        #    value when the config declares none — target_tokens/max_tokens absent).
        target = int(
            chunker_config.get("target_tokens")
            or chunker_config.get("max_tokens")
            or base.target_chunk_tokens
        )
        overlap = int(chunker_config.get("overlap_tokens") or 0)
        return base.model_copy(
            update={
                "target_chunk_tokens": target,
                "chunk_overlap_ratio": (overlap / target if target else 0.0),
            }
        )


__all__ = ["EstimateOverrideMerger"]
