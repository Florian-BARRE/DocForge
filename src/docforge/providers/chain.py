# ====== Code Summary ======
# Generic provider chain with ordered escalation.  Tries each provider in sequence;
# escalates to the next when escalate_if(result) returns True (e.g. low OCR confidence).

from __future__ import annotations

from typing import Any, Awaitable, Callable, Generic, TypeVar

from loggerplusplus import LoggerClass

T = TypeVar("T")


class ProviderChain(LoggerClass, Generic[T]):
    """
    Ordered list of providers with confidence-based escalation.

    Each call is dispatched to the first provider whose result satisfies the inverse
    of ``escalate_if``.  If all providers escalate or raise, the chain returns None.

    Usage::

        ocr_chain = ProviderChain(
            providers=[paddle_ocr, mistral_ocr],
            escalate_if=lambda r: r.confidence < 0.85,
        )
        result = await ocr_chain.call(lambda p: p.extract(img_bytes, hint))
    """

    def __init__(
        self,
        providers: list[T],
        escalate_if: Callable[[Any], bool],
    ) -> None:
        """
        Initialize the provider chain.

        Args:
            providers (list[T]): Ordered list of providers to try (first = preferred).
            escalate_if (Callable[[Any], bool]): Predicate on the provider result;
                returns True when the result is unsatisfactory and the next provider
                should be tried (e.g. ``lambda r: r.confidence < 0.85``).
        """
        LoggerClass.__init__(self)
        self._providers: list[T] = providers
        self._escalate_if: Callable[[Any], bool] = escalate_if

    @property
    def providers(self) -> list[T]:
        """Read-only access to the ordered provider list."""
        return self._providers

    @property
    def first_provider_name(self) -> str:
        """Name of the first (preferred) provider, for fingerprinting."""
        p = self._providers[0] if self._providers else None
        return getattr(p, "name", "unknown") if p else "none"

    def provider_chain_signature(self) -> str:
        """Comma-joined 'name:version' signature for all providers — used in fingerprints."""
        parts: list[str] = []
        for p in self._providers:
            name = getattr(p, "name", "unknown")
            version = getattr(p, "version", "0")
            parts.append(f"{name}:{version}")
        return ",".join(parts)

    async def call(
        self,
        fn: Callable[[T], Awaitable[Any]],
    ) -> Any | None:
        """
        Invoke ``fn`` on each provider in order until a satisfactory result is obtained.

        Args:
            fn (Callable[[T], Awaitable[Any]]): Coroutine factory — receives the current
                provider instance.  Example::

                    await chain.call(lambda p: p.extract(img, hint))

        Returns:
            Any | None: First satisfactory result; None if all providers exhausted.
        """
        # 1. Try each provider in declared order
        for provider in self._providers:
            provider_name = getattr(provider, "name", repr(provider))
            try:
                result = await fn(provider)

                # 2. Check if this result is good enough or needs escalation
                if self._escalate_if(result):
                    self.logger.debug(
                        f"ProviderChain: escalating from '{provider_name}' "
                        f"(escalate_if=True)"
                    )
                    continue

                # 3. Satisfactory result — return immediately
                self.logger.debug(
                    f"ProviderChain: '{provider_name}' succeeded"
                )
                return result

            except Exception as exc:
                # 4. Provider raised — treat as escalation
                self.logger.warning(
                    f"ProviderChain: provider '{provider_name}' raised "
                    f"{type(exc).__name__}: {exc} — trying next"
                )

        # 5. All providers failed or escalated
        self.logger.warning(
            f"ProviderChain: all {len(self._providers)} provider(s) exhausted, "
            f"returning None"
        )
        return None
