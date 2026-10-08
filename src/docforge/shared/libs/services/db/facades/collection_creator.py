# ====== Code Summary ======
# CollectionCreator — creates a collection's contract + FULL metadata schema + the version-1 config
# snapshot in ONE transaction, after the fail-fast vector-slug guard. A create that loses the
# collection-name UNIQUE race surfaces as DuplicateCollectionNameError (a 409), never a driver 500.

# ====== Third-Party Library Imports ======
from loggerplusplus import LoggerClass
from sqlalchemy.exc import IntegrityError

# ====== Internal Project Imports ======
from shared_libs.services.db.postgresql import PostgresClient
from shared_libs.services.db.postgresql.apis import CollectionApi
from shared_libs.services.db.postgresql.tables import Collection, ConfigVersion, MetadataField

# ====== Local Project Imports ======
from .collection_name_conflict import CollectionNameConflict, DuplicateCollectionNameError
from .config_history_payloads import ConfigAuthor
from .helpers import DatabaseHelpers


class CollectionCreator(LoggerClass):
    """Fail-fast, single-transaction creation of a collection contract + schema + first snapshot."""

    def __init__(self, postgres: PostgresClient) -> None:
        """
        Args:
            postgres (PostgresClient): The tabular truth the contract is written to.
        """
        LoggerClass.__init__(self)
        self._postgres = postgres

    async def create(
        self,
        collection: Collection,
        fields: list[MetadataField],
        author: ConfigAuthor | None = None,
    ) -> Collection:
        """
        Create a collection with its FULL metadata schema (including generated/chunk fields).

        Args:
            collection (Collection): The contract row.
            fields (list[MetadataField]): The whole schema — declared up front so the Qdrant
                vector space is complete at first indexing (named vectors can't be added later).
            author (ConfigAuthor | None): Who created it, stamped on the version-1 snapshot (None =
                a system creation, e.g. an import).

        Returns:
            Collection: The created row (id populated).

        Raises:
            ValueError: If two searchable fields collide on a vector slug (fail-fast, C4 guard).
            DuplicateCollectionNameError: If two creates race on the same name and this one loses the
                UNIQUE constraint (the router maps it to a clean 409, never a 500).
        """
        # 1. Fail fast before anything is written.
        DatabaseHelpers.validate_vector_slugs(fields)
        # 2. Contract + schema + the version-1 snapshot, in one transaction. The name-clash pre-check
        #    lives in the router, but a concurrent create can still slip in between it and this insert —
        #    catch that UNIQUE violation and re-raise it as the domain error the router turns into a 409.
        async with self._postgres.session() as session:
            try:
                created = await CollectionApi.create(session, collection)
            except IntegrityError as error:
                if not CollectionNameConflict.is_duplicate_name(error):
                    raise
                raise DuplicateCollectionNameError(collection.name) from error
            for field in fields:
                field.collection_id = created.id
            await CollectionApi.replace_schema(session, created.id, fields)
            await CollectionApi.add_config_version(
                session,
                ConfigVersion(
                    collection_id=created.id,
                    version=1,
                    config={"pipeline": created.pipeline, "search": created.search},
                    note="creation",
                    author_key_id=author.key_id if author is not None else None,
                    author_label=author.label if author is not None else None,
                ),
            )
        self.logger.info(f"Collection '{collection.name}' created with {len(fields)} fields")
        return created


__all__ = ["CollectionCreator"]
