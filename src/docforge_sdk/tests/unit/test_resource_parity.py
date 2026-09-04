# ====== Code Summary ======
# The drift guard: for EVERY domain resource, the Async and Sync variants must expose the SAME public
# method names and the SAME signatures (P2 relies on this to keep every async/sync pair in lockstep).
# Return annotations legitimately differ where one is awaitable, so only names + parameters compared.

# ====== Standard Library Imports ======
import inspect

# ====== Third-Party Library Imports ======
import pytest

# ====== Local Project Imports ======
from docforge_sdk.resources.audit import AsyncAudit, SyncAudit
from docforge_sdk.resources.auth import AsyncAuth, SyncAuth
from docforge_sdk.resources.blobs import AsyncBlobs, SyncBlobs
from docforge_sdk.resources.collections import AsyncCollections, SyncCollections
from docforge_sdk.resources.corpus import AsyncCorpus, SyncCorpus
from docforge_sdk.resources.documents import AsyncDocuments, SyncDocuments
from docforge_sdk.resources.explorer import AsyncExplorer, SyncExplorer
from docforge_sdk.resources.health import AsyncHealth, SyncHealth
from docforge_sdk.resources.jobs import AsyncJobs, SyncJobs
from docforge_sdk.resources.pipelines import AsyncPipelines, SyncPipelines
from docforge_sdk.resources.search import AsyncSearch, SyncSearch
from docforge_sdk.resources.snippets import AsyncSnippets, SyncSnippets
from docforge_sdk.resources.transfers import AsyncTransfers, SyncTransfers

# Every (async, sync) resource pair that must stay in lockstep.
_PAIRS: list[tuple[type, type]] = [
    (AsyncAuth, SyncAuth),
    (AsyncHealth, SyncHealth),
    (AsyncCollections, SyncCollections),
    (AsyncDocuments, SyncDocuments),
    (AsyncExplorer, SyncExplorer),
    (AsyncSearch, SyncSearch),
    (AsyncJobs, SyncJobs),
    (AsyncBlobs, SyncBlobs),
    (AsyncPipelines, SyncPipelines),
    (AsyncTransfers, SyncTransfers),
    (AsyncAudit, SyncAudit),
    (AsyncCorpus, SyncCorpus),
    (AsyncSnippets, SyncSnippets),
]


def _public_methods(cls: type) -> set[str]:
    """Return the names of a class's public (non-underscore) callables."""
    return {name for name in dir(cls) if not name.startswith("_") and callable(getattr(cls, name))}


def _parameters(cls: type, method: str) -> list[inspect.Parameter]:
    """Return the parameter objects of a method, ignoring the return annotation."""
    return list(inspect.signature(getattr(cls, method)).parameters.values())


@pytest.mark.parametrize(("async_cls", "sync_cls"), _PAIRS)
def test_async_and_sync_expose_same_public_methods(async_cls: type, sync_cls: type) -> None:
    assert _public_methods(async_cls) == _public_methods(sync_cls)


@pytest.mark.parametrize(("async_cls", "sync_cls"), _PAIRS)
def test_async_and_sync_signatures_match(async_cls: type, sync_cls: type) -> None:
    for method in _public_methods(async_cls):
        assert _parameters(async_cls, method) == _parameters(sync_cls, method), method
