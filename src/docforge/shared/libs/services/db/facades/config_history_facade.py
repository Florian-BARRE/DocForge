# ====== Code Summary ======
# ConfigHistoryFacade — the read side of a collection's versioned config history (config_version):
# a paginated newest-first listing (+ the predecessor row for change summaries) and a single version.
# Writes never go through here — every version is minted by CollectionConfigWriter under the
# collection row lock (PATCH, stage apply, snippet apply, restore).

# ====== Standard Library Imports ======
import uuid

# ====== Internal Project Imports ======
from loggerplusplus import LoggerClass

from shared_libs.services.db.postgresql import PostgresClient
from shared_libs.services.db.postgresql.apis import ConfigVersionApi
from shared_libs.services.db.postgresql.tables import ConfigVersion

# ====== Local Project Imports ======
from .config_history_payloads import ConfigVersionPage


class ConfigHistoryFacade(LoggerClass):
    """Read access to the config-version history of a collection."""

    def __init__(self, postgres: PostgresClient) -> None:
        LoggerClass.__init__(self)
        self._postgres = postgres

    async def list_page(
        self, collection_id: uuid.UUID, limit: int, offset: int
    ) -> ConfigVersionPage:
        """
        Read one newest-first page of the history.

        Args:
            collection_id (uuid.UUID): The collection whose history is listed.
            limit (int): The page size (>= 1).
            offset (int): The number of newer versions to skip (>= 0).

        Returns:
            ConfigVersionPage: The page rows, the predecessor of its last row, and the total count.
        """
        # 1. Fetch one row past the page: it is the older neighbour the last item is diffed against.
        async with self._postgres.session() as session:
            rows = await ConfigVersionApi.page(session, collection_id, limit, offset)
            total = await ConfigVersionApi.count(session, collection_id)
        # 2. Split the page from its predecessor.
        predecessor = rows[limit] if len(rows) > limit else None
        return ConfigVersionPage(items=rows[:limit], predecessor=predecessor, total=total)

    async def get(self, collection_id: uuid.UUID, version: int) -> ConfigVersion | None:
        """
        Read one config version by number.

        Args:
            collection_id (uuid.UUID): The owning collection.
            version (int): The per-collection version number.

        Returns:
            ConfigVersion | None: The snapshot row (holding REAL secrets — mask before serving it).
        """
        async with self._postgres.session() as session:
            return await ConfigVersionApi.get(session, collection_id, version)


__all__ = ["ConfigHistoryFacade"]
