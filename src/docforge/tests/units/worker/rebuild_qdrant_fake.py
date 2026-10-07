"""An in-memory fake of the AsyncQdrantClient slice an index rebuild touches, with Qdrant's alias
semantics (an alias can't shadow a collection; deleting a physical collection drops its aliases;
deleting an alias NAME is a no-op) and collection metadata (the COMPLETE stamp). Shared by the
rebuild store / self-heal tests.
"""

# ====== Standard Library Imports ======
import uuid
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock

# ====== Third-Party Library Imports ======
from qdrant_client import models

# ====== Internal Project Imports ======
from shared_libs.services.db.facades.store_rebuild_facade import StoreRebuildFacade
from shared_libs.services.db.facades.store_swapper import StoreSwapper
from shared_libs.services.db.postgresql.apis import CollectionApi
from shared_libs.services.db.qdrant import QdrantCollectionApi
from shared_libs.services.db.qdrant.apis.alias_api import COMPLETE_MARKER

DENSE = {"content_dense", "meta_topic_dense"}
SPARSE = {"content_bm25", "meta_topic_bm25"}


class FakeQdrant:
    """The slice of AsyncQdrantClient the rebuild touches, with Qdrant's alias semantics."""

    def __init__(self) -> None:
        self.collections: dict[str, dict] = {}
        self.aliases: dict[str, str] = {}
        self.calls: list[tuple] = []
        self.fail_upsert = False
        self.alias_failures = 0
        self.fail_delete = False

    def _resolve(self, name: str) -> str:
        return self.aliases.get(name, name)

    def add(
        self, name: str, dense: set[str], sparse: set[str], points: list, complete: bool = False
    ) -> None:
        metadata = {COMPLETE_MARKER: True} if complete else None
        self.collections[name] = {
            "dense": dense,
            "sparse": sparse,
            "points": points,
            "metadata": metadata,
        }

    async def get_aliases(self):
        listed = [SimpleNamespace(alias_name=a, collection_name=c) for a, c in self.aliases.items()]
        return SimpleNamespace(aliases=listed)

    async def collection_exists(self, name: str) -> bool:
        return name in self.collections or name in self.aliases

    async def get_collections(self):
        return SimpleNamespace(collections=[SimpleNamespace(name=n) for n in self.collections])

    async def get_collection(self, name: str):
        spec = self.collections[self._resolve(name)]
        params = SimpleNamespace(
            vectors={key: SimpleNamespace(size=4) for key in spec["dense"]},
            sparse_vectors={key: object() for key in spec["sparse"]},
        )
        config = SimpleNamespace(params=params, metadata=spec["metadata"])
        return SimpleNamespace(config=config, payload_schema={})

    async def update_collection(self, collection_name: str, metadata: dict) -> None:
        self.calls.append(("update_collection", collection_name))
        self.collections[self._resolve(collection_name)]["metadata"] = metadata

    async def count(self, collection_name: str, exact: bool):
        return SimpleNamespace(
            count=len(self.collections[self._resolve(collection_name)]["points"])
        )

    async def create_payload_index(self, **kwargs) -> None:
        self.calls.append(("create_payload_index", kwargs["collection_name"]))

    async def scroll(self, collection_name, limit, offset, with_payload, with_vectors):
        points = self.collections[self._resolve(collection_name)]["points"]
        start = offset or 0
        nxt = start + limit if start + limit < len(points) else None
        return points[start : start + limit], nxt

    async def upsert(self, collection_name, points, wait):
        if self.fail_upsert:
            raise RuntimeError("upsert exploded")
        self.collections[self._resolve(collection_name)]["points"].extend(points)

    async def update_collection_aliases(self, change_aliases_operations) -> None:
        self.calls.append(("update_aliases", len(change_aliases_operations)))
        if self.alias_failures:
            self.alias_failures -= 1
            raise RuntimeError("alias exploded")
        for op in change_aliases_operations:
            if isinstance(op, models.DeleteAliasOperation):
                self.aliases.pop(op.delete_alias.alias_name)
            else:
                alias = op.create_alias.alias_name
                if alias in self.collections or alias in self.aliases:
                    raise RuntimeError("an alias cannot shadow an existing name")
                self.aliases[alias] = op.create_alias.collection_name

    async def delete_collection(self, name: str) -> None:
        self.calls.append(("delete_collection", name))
        if self.fail_delete:
            raise RuntimeError("delete exploded")
        if self.collections.pop(name, None) is not None:
            self.aliases = {a: c for a, c in self.aliases.items() if c != name}


def record(point_id: int, document_id: str) -> models.Record:
    """A stored point carrying content vectors, a meta BM25 vector and an undeclared legacy one."""
    sparse = models.SparseVector(indices=[1], values=[0.5])
    return models.Record(
        id=point_id,
        payload={"document_id": document_id},
        vector={
            "content_dense": [0.1, 0.2, 0.3, 0.4],
            "content_bm25": sparse,
            "meta_topic_bm25": sparse,
            "legacy_vec": [1.0],
        },
    )


def install(monkeypatch) -> FakeQdrant:
    """A fake whose schema-driven ``ensure`` declares the CURRENT vectors on the temp store."""
    client = FakeQdrant()

    async def _ensure(raw, name, **kwargs) -> None:
        raw.add(name, set(DENSE), set(SPARSE), [])

    monkeypatch.setattr(QdrantCollectionApi, "ensure", staticmethod(_ensure))
    monkeypatch.setattr(CollectionApi, "get_schema", staticmethod(AsyncMock(return_value=[])))
    return client


def postgres() -> SimpleNamespace:
    """A postgres stub whose session() yields a dummy session."""

    @asynccontextmanager
    async def _session():
        yield object()

    return SimpleNamespace(session=_session)


def facade(fake: FakeQdrant) -> StoreRebuildFacade:
    """A StoreRebuildFacade over the fake (no alias-retry sleep)."""
    qdrant = SimpleNamespace(raw=fake)
    return StoreRebuildFacade(postgres(), qdrant, StoreSwapper(qdrant, alias_backoff_s=0.0))


def new_id() -> uuid.UUID:
    """A fresh collection id."""
    return uuid.uuid4()
