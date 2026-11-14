# ====== Code Summary ======
# ApiRunner — drives every public method of a static data-access API class against a
# RecordingSession, from a table of fixed call specs, and renders what each one did as one stable
# string. Shared by the JobApi / DocumentApi statement goldens.

# ====== Standard Library Imports ======
import inspect
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

# ====== Local Project Imports ======
from .recording_session import RecordingSession, SqlRenderer

#: Separates the operations of one method in a rendered trace.
OPERATION_SEPARATOR = "\n--\n"


@dataclass(frozen=True)
class CallSpec:
    """One deterministic invocation of an API method.

    Attributes:
        method (str): The public method name on the API class.
        variant (str): "" for the default call, else a label (``"all-filters"``) for a branch.
        build (Callable): ``build(session) -> awaitable`` — the call with fixed arguments.
        entity_state (dict): Attributes the row returned by ``session.get`` starts with, to run a
            guarded transition from a chosen state (empty: every attribute reads as a mock).
    """

    method: str
    variant: str
    build: Callable[[Any], Any]
    entity_state: dict[str, Any] = field(default_factory=dict)

    @property
    def key(self) -> str:
        """The golden key: ``method`` or ``method[variant]``."""
        return f"{self.method}[{self.variant}]" if self.variant else self.method


class ApiRunner:
    """Runs call specs and renders what they asked the database to do."""

    @staticmethod
    def public_methods(api: type) -> list[str]:
        """The sorted public (non-underscore) callable attributes of ``api``."""
        return sorted(
            name for name in dir(api) if not name.startswith("_") and callable(getattr(api, name))
        )

    @staticmethod
    async def run(spec: CallSpec) -> tuple[str, str | None]:
        """Run ``spec`` on a fresh RecordingSession and render the operations it recorded.

        A synchronous method that returns a statement (``events_query``) is rendered directly. An
        exception raised AFTER the recorded operations (a mock value the method cannot digest) is
        swallowed on purpose: only the operations are characterized.

        Args:
            spec (CallSpec): The call to run.

        Returns:
            tuple[str, str | None]: The operations joined by ``OPERATION_SEPARATOR`` (empty when none
                were recorded), and the name of the swallowed exception, if any (diagnostics only).
        """
        session = RecordingSession(spec.entity_state)
        error: str | None = None
        try:
            outcome = spec.build(session)
            if inspect.isawaitable(outcome):
                await outcome
            else:
                session.operations.append("statement:\n" + SqlRenderer.render(outcome))
        except Exception as exc:  # noqa: BLE001 - see docstring
            error = type(exc).__name__
        return OPERATION_SEPARATOR.join(session.operations), error

    @classmethod
    async def trace(cls, spec: CallSpec) -> str:
        """The rendered operations of ``spec`` (see ``run``)."""
        return (await cls.run(spec))[0]
