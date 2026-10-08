# ====== Code Summary ======
# EmbedCallPolicy — the per-endpoint call policy one embed axis runs under: its retry budget, backoff,
# endpoint (the limiter key — empty for an in-process encoder) and concurrency cap. The embed node's
# resilient retry/split frame and its limiter slot read ONLY this, so a dense slot and a sparse slot
# pointing at different servers each retry and queue under their own policy, while a combined call
# runs under the one shared endpoint's policy.

# ====== Standard Library Imports ======
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class EmbedCallPolicy:
    """The retry + limiter policy of one embed call site (an axis, or the combined call)."""

    max_retries: int = 3
    retry_backoff_seconds: float = 1.5
    endpoint: str = ""
    max_concurrency: int | None = None
    timeout_seconds: float = 60.0

    @classmethod
    def from_config(cls, config: Any) -> "EmbedCallPolicy":
        """
        Read a policy off any config carrying the shared retry/endpoint knobs (missing → defaults).

        Args:
            config (Any): A provider slot config or a single-provider embed config.

        Returns:
            EmbedCallPolicy: The policy (an in-process provider has no endpoint → no limiter slot).
        """
        return cls(
            max_retries=getattr(config, "max_retries", 3),
            retry_backoff_seconds=getattr(config, "retry_backoff_seconds", 1.5),
            endpoint=getattr(config, "base_url", "") or "",
            max_concurrency=getattr(config, "max_concurrency", None),
            timeout_seconds=getattr(config, "timeout_seconds", 60.0),
        )


__all__ = ["EmbedCallPolicy"]
