<div align="center">

<img src="https://raw.githubusercontent.com/Florian-BARRE/DocForge/main/docs/assets/wordmark.svg" alt="DocForge" width="320" />

### INGESTION, FORGED

**The typed Python client for DocForge** — async + sync, fully type-hinted, zero server-tree dependency.

[![PyPI](https://img.shields.io/pypi/v/docforge-sdk?label=docforge-sdk&color=ef5b1e)](https://pypi.org/project/docforge-sdk/)
[![Python](https://img.shields.io/pypi/pyversions/docforge-sdk?color=ef5b1e)](https://pypi.org/project/docforge-sdk/)
[![License](https://img.shields.io/badge/license-MIT-blue)](https://github.com/Florian-BARRE/DocForge/blob/main/src/docforge_sdk/LICENSE)

</div>

---

A typed Python client for the [DocForge](https://github.com/Florian-BARRE/DocForge) REST API. It
ships **both** an asynchronous and a synchronous client with an identical surface, is fully
type-hinted (`py.typed`), and has **zero dependency on the DocForge server tree** — it is a
clean-room client that talks to the API over HTTP only (`httpx` + `pydantic` + hand-written models
that mirror the public REST contract), so it can be vendored or published independently.

## Install

```bash
pip install docforge-sdk
```

## Async usage

```python
import asyncio

from docforge_sdk import AsyncClient, SearchRequest


async def main() -> None:
    async with AsyncClient("http://localhost:10040", api_token="df_root_...") as client:
        collections = await client.collections.list()
        for collection in collections:
            print(collection.id, collection.name)

        hits = await client.search.search(
            collections[0].id,
            SearchRequest(query="quarterly revenue", limit=5),
        )
        for hit in hits.hits:
            print(hit.score, hit.text)


asyncio.run(main())
```

## Sync usage

```python
from docforge_sdk import Client, SearchRequest

with Client("http://localhost:10040", api_token="df_root_...") as client:
    collections = client.collections.list()
    hits = client.search.search(
        collections[0].id,
        SearchRequest(query="quarterly revenue", limit=5),
    )
    for hit in hits.hits:
        print(hit.score, hit.text)
```

The two clients expose the same resources and method signatures; the sync methods are the async ones
without `await`. Available resource groups: `auth`, `health`, `collections`, `documents`, `explorer`,
`search`, `jobs`, `blobs`, `pipelines`.

## License

MIT — see [LICENSE](LICENSE). This SDK is deliberately licensed **MIT even though the parent DocForge
repository is GPLv3**: it is a standalone, clean-room client (HTTP models only, no server code), so a
permissive per-directory license is intentional and lets any project depend on it freely.

## Publishing (maintainers)

Releases publish to PyPI via **Trusted Publishing (OIDC)** — there is no API token stored in the
repo. To cut a release, tag a commit with the `sdk-v<version>` prefix (the version must match
`docforge_sdk/_version.py`) and push the tag:

```bash
git tag sdk-v0.1.0
git push origin sdk-v0.1.0
```

The `.github/workflows/release-sdk.yml` workflow then builds and uploads the sdist + wheel.

**One-time PyPI setup** (done once by the maintainer, before the first release):

1. Reserve the project name `docforge-sdk` on PyPI.
2. Under the project's *Publishing* settings, add a **GitHub trusted publisher** with:
   - Owner: `Florian-BARRE`
   - Repository: `docforge`
   - Workflow name: `release-sdk.yml`
   - Environment: `pypi`
