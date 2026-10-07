"""EXECUTES the config-version authorship against a real Postgres (PG-only facade paths, qdrant/s3
None): creation and a config write stamp ``author_key_id`` + ``author_label``, the history read facade
pages them newest-first with the predecessor row, and deleting the authoring key SETs the FK NULL
while the label snapshot survives (migration a8e3b5d1c9f4)."""

# ====== Standard Library Imports ======
import uuid
from collections.abc import AsyncIterator

# ====== Third-Party Library Imports ======
import pytest
from sqlalchemy import delete

# ====== Internal Project Imports ======
from shared_libs.services.db.facades import ConfigAuthor, ConfigHistoryFacade
from shared_libs.services.db.facades.collections_facade import CollectionsFacade
from shared_libs.services.db.postgresql import PostgresClient
from shared_libs.services.db.postgresql.apis import AuthApi
from shared_libs.services.db.postgresql.tables import ApiKey, AppUser, Collection

pytestmark = pytest.mark.db


@pytest.fixture
async def client(migrated_db_dsn: str) -> AsyncIterator[PostgresClient]:
    """A PostgresClient against the head-migrated throwaway db (disposed on teardown)."""
    postgres = PostgresClient(migrated_db_dsn)
    try:
        yield postgres
    finally:
        await postgres.dispose()


async def _key(client: PostgresClient) -> ApiKey:
    """A fresh user + API key (the author FK target)."""
    async with client.session() as session:
        user = await AuthApi.create_user(
            session, AppUser(username=f"u-{uuid.uuid4().hex[:8]}", password_hash="x")
        )
        return await AuthApi.create_key(
            session,
            ApiKey(user_id=user.id, name="ci-bot", key_hash=uuid.uuid4().hex, prefix="df_x"),
        )


async def test_author_is_recorded_and_survives_key_deletion(client: PostgresClient) -> None:
    key = await _key(client)
    author = ConfigAuthor(key_id=key.id, label="ci-bot")
    facade = CollectionsFacade(client, None, None)
    created = await facade.create(
        Collection(
            name=f"hist-{uuid.uuid4().hex[:8]}",
            supported_formats=["pdf"],
            max_file_size_bytes=10_000_000,
            pipeline={},
            search={},
        ),
        [],
        author=author,
    )
    await facade.update_config(created.id, search={"x": 1}, note="edit", author=author)
    await facade.update_config(created.id, search={"x": 2}, note="anon")

    # 1. Newest first, the predecessor of the page's last item fetched alongside.
    history = ConfigHistoryFacade(client)
    page = await history.list_page(created.id, limit=2, offset=0)
    assert page.total == 3 and [r.version for r in page.items] == [3, 2]
    assert page.predecessor is not None and page.predecessor.version == 1
    assert (page.items[0].author_key_id, page.items[0].author_label) == (None, None)
    assert (page.items[1].author_key_id, page.items[1].author_label) == (key.id, "ci-bot")

    # 2. Deleting the key unlinks the id (ON DELETE SET NULL) but keeps the label snapshot.
    async with client.session() as session:
        await session.execute(delete(ApiKey).where(ApiKey.id == key.id))
    v1 = await history.get(created.id, 1)
    assert v1 is not None and v1.author_key_id is None and v1.author_label == "ci-bot"
    assert await history.get(created.id, 99) is None
