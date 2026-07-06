# ---------------------- Low-level client ---------------------- #
from .client import PostgresClient

# ---------------------- ORM schema ---------------------- #
# The models live under `.tables` (one file per table, grouped by domain); `Base` gathers them all.
from .tables import Base

# ------------------- Public API ------------------- #
__all__ = ["PostgresClient", "Base"]
