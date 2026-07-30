# docforge-sdk

A typed Python client for the DocForge REST API. It ships **both** an asynchronous and a
synchronous client with an identical surface, is fully type-hinted, and has **zero dependency on the
DocForge server tree** — it talks to the API over HTTP only (`httpx` + `pydantic`), so it can be
vendored or published independently.

## Install

```bash
uv add docforge-sdk        # once published
# or, from a local checkout:
uv add --editable ../docforge_sdk
```

## Async usage

```python
from docforge_sdk import AsyncClient, Capability, KeyPermissions

async def main() -> None:
    async with AsyncClient("http://localhost:10040", api_token="df_root_...") as client:
        created = await client.auth.create_key(
            name="ci-runner",
            permissions=KeyPermissions(capabilities=[Capability.READ], collections=["*"]),
        )
        print(created.key)  # plaintext, shown exactly once
        keys = await client.auth.list_keys()
        await client.auth.revoke_key(keys[0].id)
```

## Sync usage

```python
from docforge_sdk import Client

with Client("http://localhost:10040", api_token="df_root_...") as client:
    created = client.auth.create_key(name="ci-runner")
    print(created.key)
```

The two clients expose the same resources and method signatures; the sync methods are the async ones
without `await`.
