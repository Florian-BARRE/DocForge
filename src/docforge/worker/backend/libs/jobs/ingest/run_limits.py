# ====== Code Summary ======
# RunLimits — the two per-run budgets resolved from the collection's request and the operator's
# ceilings: the wall-clock job timeout (fail-fast above arq's hard cap) and the effective trace level
# (the collection's verbosity clamped by WORKER_TRACE_MAX_VERBOSITY). Pure; shared by the full run and
# the replay run.

# ====== Internal Project Imports ======
from shared_libs.pipelines.engine import TraceLevel


class RunLimits:
    """Static-only: resolve a run's job timeout and trace level."""

    def __new__(cls, *args: object, **kwargs: object) -> None:
        raise TypeError("RunLimits is a static-only class and cannot be instantiated.")

    @staticmethod
    def resolve_job_timeout(
        collection_job_timeout: float | None,
        default_job_timeout: float,
        max_job_timeout: float,
    ) -> float:
        """Resolve the run's wall-clock job timeout, failing fast on a value above the hard ceiling.

        The engine's per-run job timeout must stay authoritative — it fires BEFORE arq's outer
        job_timeout (which is ``max_job_timeout`` + grace). A per-collection job timeout above the
        ceiling would be silently truncated by arq's cap, so it is surfaced here BY NAME as a
        configuration error rather than applied partially — the operator raises the ceiling or lowers
        the collection's job timeout.

        Args:
            collection_job_timeout (float | None): The collection's per-run override (None → default).
            default_job_timeout (float): The worker's global default job timeout.
            max_job_timeout (float): The hard ceiling any single run may request.

        Returns:
            float: The wall-clock job timeout to hand the engine.

        Raises:
            ValueError: The requested per-collection job timeout exceeds the hard ceiling.
        """
        job_timeout = collection_job_timeout or default_job_timeout
        if job_timeout > max_job_timeout:
            raise ValueError(
                f"collection job_timeout_seconds={collection_job_timeout}s exceeds the worker's hard "
                f"ceiling WORKER_JOB_TIMEOUT_MAX_SECONDS={max_job_timeout}s — raise the ceiling or "
                f"lower the per-collection job timeout (the engine job timeout must stay under "
                f"arq's outer cap)"
            )
        return job_timeout

    @staticmethod
    def resolve_trace_level(collection_verbosity: str | None, ceiling: str) -> TraceLevel:
        """Resolve the run's effective trace level: the collection's request clamped by the ceiling.

        The per-collection ``trace_verbosity`` ("shape"/"full", None → "shape") is honoured only up
        to the operator ceiling ``WORKER_TRACE_MAX_VERBOSITY`` — so an operator can forbid "full"
        fleet-wide. An unrecognised value degrades to "shape" (the safe default: no raw content at
        rest), never a crash.

        Args:
            collection_verbosity (str | None): The collection's ``trace_verbosity`` (None → shape).
            ceiling (str): The operator ceiling (WORKER_TRACE_MAX_VERBOSITY).

        Returns:
            TraceLevel: ``min(collection, ceiling)`` in the off < shape < full ordering.
        """
        valid = {level.value for level in TraceLevel}
        requested = (
            TraceLevel(collection_verbosity) if collection_verbosity in valid else TraceLevel.SHAPE
        )
        cap = TraceLevel(ceiling) if ceiling in valid else TraceLevel.SHAPE
        return requested.clamp(cap)


__all__ = ["RunLimits"]
