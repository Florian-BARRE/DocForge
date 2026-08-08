# ====== Code Summary ======
# NetworkRetry — the ONE bounded, transient-only retry loop shared by every network-calling node that
# does NOT own a bespoke resilience skeleton. Modelled on the VLM base's loop (1 initial call +
# max_retries retries, transient = timeout/transport/429/5xx, backoff = base * (attempt + 1),
# non-transient re-raised at once), lifted out so llm/ocr/structgen/gotenberg/pp_structure share it
# instead of each hand-rolling a loop. VLM and embed keep their OWN loops (embed additionally splits
# the batch), so they are deliberately NOT routed through here. It runs INSIDE a node's run(), reading
# the node's config fields — no DB/S3, the pure invariant holds.

# ====== Standard Library Imports ======
import asyncio
from collections.abc import Awaitable, Callable
from typing import TypeVar

# ====== Third-Party Library Imports ======
import httpx
import openai
from loggerplusplus import loggerplusplus

_Result = TypeVar("_Result")

# HTTP statuses worth a retry: rate-limit (429) and the transient 5xx server errors. A 4xx (auth, bad
# request) is a permanent misconfiguration whose retry would only waste a paid call.
_TRANSIENT_STATUS = frozenset({429, 500, 502, 503, 504})


class NetworkRetry:
    """Static bounded-retry helper shared by the network nodes without a bespoke retry loop."""

    logger = loggerplusplus.bind(identifier="NetworkRetry")

    def __new__(cls, *args: object, **kwargs: object) -> None:
        raise TypeError("NetworkRetry is a static-only class and cannot be instantiated.")

    @staticmethod
    def is_transient(error: Exception) -> bool:
        """Whether a provider error is worth retrying: a timeout, a transport blip, or a 429/5xx.

        Covers BOTH surfaces a provider call raises through: raw ``httpx`` (used by the direct-HTTP
        nodes — gotenberg, pp_structure, ocr) and the ``openai`` SDK errors LangChain surfaces
        (llm, structgen). Everything else (a 4xx, a parse error) is permanent and re-raised at once.
        """
        if isinstance(error, httpx.TimeoutException | httpx.TransportError):
            return True
        if isinstance(error, httpx.HTTPStatusError):
            return error.response.status_code in _TRANSIENT_STATUS
        return isinstance(
            error,
            openai.APITimeoutError
            | openai.APIConnectionError
            | openai.RateLimitError
            | openai.InternalServerError,
        )

    @classmethod
    async def run(
        cls,
        operation: Callable[[], Awaitable[_Result]],
        *,
        max_retries: int,
        retry_backoff_seconds: float,
        label: str,
    ) -> _Result:
        """
        Run one async network operation with a bounded, transient-only retry.

        Args:
            operation (Callable[[], Awaitable]): The zero-arg async call to run (a closure over the
                node's request); re-invoked from scratch on each retry.
            max_retries (int): Retries after the initial attempt (0 = one shot, no retry).
            retry_backoff_seconds (float): Base delay; the sleep before retry N is base * (N + 1).
            label (str): A short caller identity ("<family> '<kind>'") named in the retry log line.

        Returns:
            The operation's result on the first successful attempt.

        Raises:
            Exception: The last error — re-raised immediately when non-transient, or after the
                retries are exhausted so the graph's own escalation (OnFailure/ScoreBelow) takes over.
        """
        for attempt in range(max_retries + 1):  # 1 initial call + max_retries retries
            try:
                return await operation()
            except Exception as error:  # noqa: BLE001 — re-raised below unless a bounded transient
                if not cls.is_transient(error) or attempt == max_retries:
                    raise
                cls.logger.warning(
                    f"{label} transient error (attempt {attempt + 1}/{max_retries + 1}): {error!r}"
                )
                await asyncio.sleep(retry_backoff_seconds * (attempt + 1))
        # Unreachable: the loop either returns a result or raises on the final attempt.
        raise AssertionError("unreachable")


__all__ = ["NetworkRetry"]
