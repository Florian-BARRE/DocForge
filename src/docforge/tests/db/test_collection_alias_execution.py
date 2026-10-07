"""EXECUTES the collection-alias table + facade against a real Postgres (migration b4d9e2a7c6f1):
create / atomic re-point / delete through ``CollectionAliasFacade``, the name-clash refusal, the
collection delete refused while an alias targets it, and the schema backstops — the name primary key
(unique), the slug CHECK, and the ``collection_id`` FK (unknown target refused, ON DELETE RESTRICT)."""

# ====== Standard Library Imports ======
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime

# ====== Third-Party Library Imports ======
import pytest
from sqlalchemy import delete
from sqlalchemy.exc import IntegrityError

# ====== Internal Project Imports ======
from shared_libs.services.db.facades import (
    CollectionAliasedError,
    CollectionAliasInUseError,
    CollectionAliasNameClashError,
    CollectionAliasTargetMissingError,
)
from shared_libs.services.db.facades.collection_alias_facade import CollectionAliasFacade
from shared_libs.services.db.facades.collections_facade import CollectionsFacade
from shared_libs.services.db.postgresql import PostgresClient
from shared_libs.services.db.postgresql.tables import (
    ApiKey,
    AppUser,
    Collection,
    CollectionAlias,
    UserRole,
)

pytestmark = pytest.mark.db


@pytest.fixture
async def client(migrated_db_dsn: str) -> AsyncIterator[PostgresClient]:
    """A PostgresClient against the head-migrated throwaway db (disposed on teardown)."""
    postgres = PostgresClient(migrated_db_dsn)
    try:
        yield postgres
    finally:
        await postgres.dispose()


async def _collection(client: PostgresClient, name: str | None = None) -> Collection:
    """A fresh, minimal collection row."""
    return await CollectionsFacade(client, None, None).create(
        Collection(
            name=name or f"alias-{uuid.uuid4().hex[:8]}",
            supported_formats=["pdf"],
            max_file_size_bytes=10_000_000,
            pipeline={},
            search={},
        ),
        [],
    )


def _alias() -> str:
    return f"al-{uuid.uuid4().hex[:8]}"


async def test_create_repoint_resolve_and_delete(client: PostgresClient) -> None:
    a, b = await _collection(client), await _collection(client)
    aliases = CollectionAliasFacade(client)
    name = _alias()

    created = await aliases.set(name, a.id)
    assert created.previous_collection_id is None and created.collection_id == a.id
    assert await aliases.targets_of([name, "al-missing"]) == {name: a.id}

    seen: list[uuid.UUID | None] = []
    moved = await aliases.set(name, b.id, seen.append)
    assert seen == [a.id] and moved.previous_collection_id == a.id
    assert await aliases.targets_of([name]) == {name: b.id}
    assert await aliases.names_for(b.id) == [name] and await aliases.names_for(a.id) == []

    assert await aliases.delete(name) is True
    assert await aliases.delete(name) is False
    assert await aliases.targets_of([name]) == {}


async def test_refusals_leave_the_alias_untouched(client: PostgresClient) -> None:
    a = await _collection(client)
    aliases = CollectionAliasFacade(client)
    name = _alias()

    with pytest.raises(CollectionAliasTargetMissingError):
        await aliases.set(name, uuid.uuid4())
    clash = await _collection(client, name=name.upper())
    with pytest.raises(CollectionAliasNameClashError):
        await aliases.set(name, a.id)
    assert await aliases.name_is_alias(clash.name) is False

    # An authorizer raising under the lock rolls the write back.
    other = _alias()
    await aliases.set(other, a.id)

    def _deny(_previous: uuid.UUID | None) -> None:
        raise PermissionError("nope")

    with pytest.raises(PermissionError):
        await aliases.delete(other, _deny)
    assert await aliases.targets_of([other]) == {other: a.id}
    assert await aliases.name_is_alias(other.upper()) is True


async def test_collection_delete_refused_while_aliased(client: PostgresClient) -> None:
    a = await _collection(client)
    aliases = CollectionAliasFacade(client)
    name = _alias()
    await aliases.set(name, a.id)

    with pytest.raises(CollectionAliasedError) as refused:
        await CollectionsFacade(client, None, None).delete(a.id)
    assert refused.value.aliases == [name]

    assert await aliases.names_for(a.id) == [name]


async def test_schema_backstops(client: PostgresClient) -> None:
    a = await _collection(client)
    name = _alias()
    async with client.session() as session:
        session.add(CollectionAlias(name=name, collection_id=a.id))

    # 1. The name is the primary key — a duplicate insert is refused.
    with pytest.raises(IntegrityError):
        async with client.session() as session:
            session.add(CollectionAlias(name=name, collection_id=a.id))

    # 2. The slug CHECK refuses an uppercase name written around the API.
    with pytest.raises(IntegrityError):
        async with client.session() as session:
            session.add(CollectionAlias(name="Bad Name", collection_id=a.id))

    # 3. The FK refuses an unknown target, and RESTRICTs a raw delete of the target.
    with pytest.raises(IntegrityError):
        async with client.session() as session:
            session.add(CollectionAlias(name=_alias(), collection_id=uuid.uuid4()))
    with pytest.raises(IntegrityError):
        async with client.session() as session:
            await session.execute(delete(Collection).where(Collection.id == a.id))


async def test_delete_refused_while_a_live_key_names_the_alias(client: PostgresClient) -> None:
    """A freed alias name would re-bind every key still naming it to whoever re-creates it: the
    delete is refused while a LIVE key carries ``alias:<name>`` (a revoked key does not count)."""
    target = await _collection(client)
    aliases = CollectionAliasFacade(client)
    name = _alias()
    await aliases.set(name, target.id)
    async with client.session() as session:
        user = AppUser(username=f"u-{uuid.uuid4().hex[:8]}", password_hash="x", role=UserRole.USER)
        session.add(user)
        await session.flush()
        live = ApiKey(
            user_id=user.id,
            name="live",
            key_hash=uuid.uuid4().hex,
            prefix="df_live",
            permissions={"capabilities": ["read_text"], "collections": [f"alias:{name}"]},
        )
        session.add(live)
        await session.flush()
        live_id = live.id

    with pytest.raises(CollectionAliasInUseError):
        await aliases.delete(name)
    assert await aliases.targets_of([name]) == {name: target.id}

    async with client.session() as session:
        key = await session.get(ApiKey, live_id)
        key.revoked_at = datetime.now(UTC)

    assert await aliases.delete(name) is True
