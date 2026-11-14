# ====== Code Summary ======
# RecordingSession — a stand-in for an AsyncSession that never touches a database. It records every
# operation a data-access method performs (``execute`` with the statement compiled against the
# PostgreSQL dialect, ``get``, ``add``, ``flush``, ``delete``…) as a list of short strings, so a test
# can pin WHAT a method asks the database to do without a database.

# ====== Standard Library Imports ======
from typing import Any
from unittest.mock import MagicMock

# ====== Third-Party Library Imports ======
from sqlalchemy.dialects import postgresql


class SqlRenderer:
    """Renders a SQLAlchemy statement to a stable, whitespace-normalised PostgreSQL string."""

    _DIALECT = postgresql.dialect()

    @classmethod
    def render(cls, statement: Any) -> str:
        """Compile ``statement`` against the PostgreSQL dialect (bind parameters stay placeholders).

        Args:
            statement (Any): A Core/ORM statement (select, update, delete, insert…).

        Returns:
            str: The compiled SQL, one trimmed line per compiler line, no trailing blank space.
        """
        compiled = str(statement.compile(dialect=cls._DIALECT))
        return "\n".join(line.strip() for line in compiled.strip().splitlines())


class _TrackedEntity:
    """An ORM-row double: every attribute assignment is recorded, every read yields a MagicMock."""

    def __init__(self, name: str, operations: list[str], state: dict[str, Any]) -> None:
        object.__setattr__(self, "_name", name)
        object.__setattr__(self, "_operations", operations)
        object.__setattr__(self, "_state", dict(state))

    def __setattr__(self, attribute: str, value: Any) -> None:
        self._operations.append(f"set:{self._name}.{attribute}={value!r}")
        self._state[attribute] = value

    def __getattr__(self, attribute: str) -> Any:
        state = object.__getattribute__(self, "_state")
        return state[attribute] if attribute in state else MagicMock()


class RecordingSession:
    """An AsyncSession double that appends one string per operation to ``operations``.

    Every ``execute`` returns a permissive MagicMock result (``rowcount`` 1) so a method can run on
    past its first statement; a method that then trips on a mock value is not a problem — the
    operations recorded before the failure are what the characterization pins.
    """

    def __init__(self, entity_state: dict[str, Any] | None = None) -> None:
        """
        Args:
            entity_state (dict[str, Any] | None): Attribute values the row returned by ``get`` starts
                with (e.g. ``{"status": DocumentStatus.PENDING}``) so a guarded transition can be run
                from a chosen state; any other attribute reads as a MagicMock.
        """
        self.operations: list[str] = []
        self._entity_state = entity_state or {}

    async def execute(self, statement: Any, *args: Any, **kwargs: Any) -> MagicMock:
        """Record the compiled statement and hand back a permissive result."""
        self.operations.append("execute:\n" + SqlRenderer.render(statement))
        result = MagicMock()
        result.rowcount = 1
        return result

    async def get(self, entity: Any, ident: Any, *args: Any, **kwargs: Any) -> _TrackedEntity:
        """Record a primary-key lookup (entity name only); the row it returns records its writes."""
        self.operations.append(f"get:{entity.__name__}")
        return _TrackedEntity(entity.__name__, self.operations, self._entity_state)

    def add(self, instance: Any) -> None:
        """Record an ORM add (class name only)."""
        self.operations.append(f"add:{type(instance).__name__}")

    def add_all(self, instances: Any) -> None:
        """Record an ORM add_all (class names, in order)."""
        self.operations.append("add_all:" + ",".join(type(i).__name__ for i in instances))

    async def delete(self, instance: Any) -> None:
        """Record an ORM delete (class name only)."""
        self.operations.append(f"delete:{type(instance).__name__}")

    async def flush(self, *args: Any, **kwargs: Any) -> None:
        """Record a flush."""
        self.operations.append("flush")

    async def refresh(self, instance: Any, *args: Any, **kwargs: Any) -> None:
        """Record a refresh (class name only)."""
        self.operations.append(f"refresh:{type(instance).__name__}")
