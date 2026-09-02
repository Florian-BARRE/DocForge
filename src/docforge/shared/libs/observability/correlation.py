# ====== Code Summary ======
# Request/job correlation id — the one value that lets an operator trace a single user action across
# the app and the worker it triggers. A process-wide ContextVar (async-safe, mirrors the MCP bearer
# contextvar and the auth principal) holds the id for the duration of a request (app) or a job
# (worker); a loguru patcher stamps it into every record's `extra` so the configured log format
# surfaces it WITHOUT touching a single call site. Shared by both apps via the `shared_libs` alias so
# the id generated on the app side and the id rebound on the worker side are the exact same field.

from __future__ import annotations

# ====== Standard Library Imports ======
import uuid
from contextvars import ContextVar, Token
from typing import Any

# ====== Third-Party Library Imports ======
from loggerplusplus import loggerplusplus

# The ambient correlation id for the current async context. None outside any request/job (e.g. at
# process boot) — the patcher then renders the neutral placeholder. Declared module-level (a single
# shared object) exactly like the MCP `incoming_docforge_token` contextvar.
_correlation_id: ContextVar[str | None] = ContextVar("docforge_correlation_id", default=None)


class CorrelationContext:
    """
    Static access to the per-request/per-job correlation id and its loguru surfacing.

    Holds no instance state: the id lives in a module-level ContextVar so it propagates safely across
    ``await`` boundaries and never bleeds between concurrent requests/jobs. ``install_log_patcher``
    wires the id into every log record; ``set``/``reset`` bracket a request or a job.
    """

    # The loguru `extra` key the configured format reads as ``{extra[correlation_id]}``. The two
    # runtime_config logging blocks reference this name as a literal in their format template (they
    # cannot import shared_libs that early), so it MUST stay in sync with the string here.
    FIELD = "correlation_id"
    # Rendered when no id is bound (boot-time logs, or a stray log outside any request/job).
    PLACEHOLDER = "-"

    logger = loggerplusplus.bind(identifier="CorrelationContext")

    def __new__(cls, *args: object, **kwargs: object) -> None:
        """Block instantiation — this is a static-only helper class."""
        raise TypeError("CorrelationContext is a static-only class and cannot be instantiated.")

    @classmethod
    def generate(cls) -> str:
        """
        Mint a fresh correlation id.

        Returns:
            str: A compact, URL/header-safe unique id (uuid4 hex, no dashes).
        """
        return uuid.uuid4().hex

    @classmethod
    def get(cls) -> str | None:
        """
        Return the correlation id bound to the current context, if any.

        Returns:
            str | None: The current id, or ``None`` when nothing is bound.
        """
        return _correlation_id.get()

    @classmethod
    def set(cls, correlation_id: str) -> Token[str | None]:
        """
        Bind a correlation id to the current context.

        Args:
            correlation_id (str): The id to bind (from an inbound header, a job arg, or ``generate``).

        Returns:
            Token: The reset token — pass it to ``reset`` in a ``finally`` to restore the prior value.
        """
        return _correlation_id.set(correlation_id)

    @classmethod
    def reset(cls, token: Token[str | None]) -> None:
        """
        Restore the correlation id the context held before the matching ``set``.

        Args:
            token (Token): The token returned by ``set``.
        """
        _correlation_id.reset(token)

    @classmethod
    def install_log_patcher(cls) -> None:
        """
        Install the loguru patcher that stamps the current correlation id onto every log record.

        The patcher runs once per emitted record (before per-handler formatting), writing the
        ambient id — or the neutral placeholder when nothing is bound — into ``record["extra"]`` so
        the configured format's ``{extra[correlation_id]}`` token always resolves. Idempotent: it
        only sets loguru's single global ``patcher`` and never touches handlers or levels, so it is
        safe to call once per process (app entrypoint / worker startup).
        """

        # 1. The per-record hook: always present the field, defaulting to the placeholder when unbound.
        def _patch(record: dict[str, Any]) -> None:
            record["extra"][cls.FIELD] = _correlation_id.get() or cls.PLACEHOLDER

        # 2. Register it as loguru's global patcher (handlers/levels untouched — patcher-only configure).
        loggerplusplus.configure(patcher=_patch)


__all__ = ["CorrelationContext"]
