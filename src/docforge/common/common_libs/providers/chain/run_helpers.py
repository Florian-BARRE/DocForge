# ====== Code Summary ======
# ChainRunHelpers — static helpers for the Chain[T, R] execution loop.
#
# Extracted from chain/core.py to keep the Chain engine file under 200 lines.
# Covers single-attempt execution (timing + exception capture), score extraction,
# and structured per-attempt log emission.  All methods are pure functions: they
# take every dependency (logger, stage name) as explicit arguments.

# ====== Standard Library Imports ======
from __future__ import annotations

import time
from collections.abc import Awaitable, Callable
from typing import Any

# ====== Third-Party Library Imports ======
from loggerplusplus import LoggerClass

# ====== Local Project Imports ======
from .models import ChainAttempt


class ChainRunHelpers:
    """
    Static helpers for the Chain[T, R] execution loop.

    Covers single-attempt execution, score extraction, and structured log emission.
    All methods take the logger and stage name as explicit parameters so the
    helpers remain stateless.
    """

    def __new__(cls, *args: object, **kwargs: object) -> None:  # type: ignore[return]
        """Block instantiation — this is a static-only helper class."""
        raise TypeError("ChainRunHelpers is a static-only class and cannot be instantiated.")

    @staticmethod
    async def run_attempt(
        provider: Any,
        fn: Callable[[Any], Awaitable[Any]],
        provider_id: str,
    ) -> tuple[ChainAttempt, Any]:
        """
        Execute a single provider call, timing it and capturing any exception.

        Returns the attempt record alongside the raw result so the gate can
        inspect it.  The ``escalated`` flag on the returned attempt is always
        ``False``; the caller must update it via ``ChainHelpers.replace_escalated``.

        Args:
            provider: Provider instance to invoke.
            fn (Callable): The user's coroutine factory.
            provider_id (str): Stable identifier extracted from the provider.

        Returns:
            tuple[ChainAttempt, Any]: The attempt record and the raw result
                (None when the call raised).
        """
        cost = float(getattr(provider, "cost_per_call", 0.0) or 0.0)
        start = time.perf_counter()
        try:
            # 1. Run the provider's coroutine; record the duration in either branch.
            result = await fn(provider)
            duration_ms = int((time.perf_counter() - start) * 1000)
            score = ChainRunHelpers.extract_score(result)
            return (
                ChainAttempt(
                    provider_id=provider_id,
                    score=score,
                    duration_ms=duration_ms,
                    succeeded=result is not None,
                    escalated=False,
                    error=None,
                    cost_usd=cost,
                ),
                result,
            )
        except Exception as exc:  # noqa: BLE001 — any failure escalates to the next provider
            # 2. Capture the exception summary; the gate will mark it as escalated.
            duration_ms = int((time.perf_counter() - start) * 1000)
            return (
                ChainAttempt(
                    provider_id=provider_id,
                    score=None,
                    duration_ms=duration_ms,
                    succeeded=False,
                    escalated=False,
                    error=f"{type(exc).__name__}: {exc}",
                    cost_usd=cost,
                ),
                None,
            )

    @staticmethod
    def extract_score(result: Any) -> float | None:
        """
        Pull score off a ScoredResult; return None when the type doesn't score.

        The import is deferred inside the method to avoid a circular dependency:
        scoring.py → (nothing in chain/); chain/ → chain_gate.py → scoring.py.
        A top-level import of ScoredResult here would create a cycle through
        chain_gate.py which already imports scoring.py at module level.

        Args:
            result (Any): The raw provider result.

        Returns:
            float | None: The quality score, or None when unavailable.
        """
        from common_libs.providers.scoring import ScoredResult  # deferred — avoids cycle

        if isinstance(result, ScoredResult):
            try:
                return result.score()
            except Exception:  # noqa: BLE001 — never let a buggy score() break the chain
                return None
        return None

    @staticmethod
    def log_attempt(
        logger: LoggerClass,
        stage: str,
        idx: int,
        total: int,
        attempt: ChainAttempt,
    ) -> None:
        """
        Emit one structured log line per attempt (operator-readable).

        Args:
            logger (LoggerClass): The chain instance's logger.
            stage (str): Human label of the stage this chain serves.
            idx (int): 1-based index of the current attempt.
            total (int): Total number of providers in the chain.
            attempt (ChainAttempt): The completed attempt record.

        Returns:
            None
        """
        from .models import ChainHelpers  # local import — avoids circular at module level

        if attempt.succeeded:
            logger.info(
                f"[CHAIN {stage}] attempt {idx}/{total} "
                f"provider={attempt.provider_id} "
                f"score={ChainHelpers.fmt_score(attempt.score)} "
                f"duration_ms={attempt.duration_ms}"
            )
        else:
            logger.warning(
                f"[CHAIN {stage}] attempt {idx}/{total} "
                f"provider={attempt.provider_id} FAILED "
                f"duration_ms={attempt.duration_ms} error={attempt.error!r}"
            )
