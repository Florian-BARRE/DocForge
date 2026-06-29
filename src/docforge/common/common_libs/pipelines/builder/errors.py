# ====== Code Summary ======
# Build-time errors for the PipelineBuilder — raised while turning a saved per-collection config into
# a live pipeline (provider unavailable, unknown category, etc.). These are distinct from the runtime
# PipelineError tree (which the engine raises during a run); a build error means the pipeline could
# never be assembled in the first place, so it fails fast before any document is processed.


class PipelineBuildError(Exception):
    """Base error raised when the PipelineBuilder cannot assemble a pipeline from a config."""


class ChainBuildError(PipelineBuildError):
    """
    A provider declared in a chain config cannot be instantiated.

    Raised when a provider's ``availability`` check fails (missing credential, endpoint, or model),
    so the misconfiguration surfaces at build time rather than mid-ingestion.
    """

    def __init__(self, category: str, provider_id: str, reason: str) -> None:
        """
        Args:
            category (str): Provider category of the chain (e.g. ``"ocr"``).
            provider_id (str): The unavailable provider's id.
            reason (str): Human-readable availability failure reason.
        """
        self.category = category
        self.provider_id = provider_id
        self.reason = reason
        super().__init__(
            f"Cannot build {category!r} chain: provider {provider_id!r} unavailable ({reason})."
        )


__all__ = ["PipelineBuildError", "ChainBuildError"]
