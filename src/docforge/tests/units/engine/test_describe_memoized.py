"""ActionNode.describe() is memoized per concrete class.

Building a node's card runs ``Config.model_json_schema()`` (a non-trivial Pydantic op), and the card
is rebuilt per request by the palette (``GET /pipelines/{key}``) and ``GET /capabilities`` (every
family × node). Node classes/Configs are immutable after import, so the card is computed ONCE per
class and reused — proven here by counting the schema build across repeated ``describe()`` /
``catalog()`` calls.
"""

from shared_libs.pipelines.registry import NodeRegistry


async def test_describe_built_once_across_repeated_calls(monkeypatch) -> None:
    node_cls = NodeRegistry.get("chunker", "fixed_size")
    # The lru_cache is shared by the one describe() function (keyed by cls); clear it so this class's
    # build is counted deterministically regardless of what earlier tests already cached.
    node_cls.describe.cache_clear()

    builds = {"n": 0}
    real_schema = node_cls.Config.model_json_schema

    def _counting_schema(*args: object, **kwargs: object):
        builds["n"] += 1
        return real_schema(*args, **kwargs)

    monkeypatch.setattr(node_cls.Config, "model_json_schema", _counting_schema)

    first = node_cls.describe()
    second = node_cls.describe()
    # catalog() rebuilds every card per call pre-fix — now it reuses the memoized one.
    NodeRegistry.catalog("chunker")
    NodeRegistry.catalog("chunker")

    assert builds["n"] == 1  # the schema is built exactly once despite four describe() paths
    assert first is second  # the same cached card instance is handed back


async def test_describe_is_keyed_per_class(monkeypatch) -> None:
    # A per-CLASS cache: two distinct node classes each cache their own card independently, so a
    # newly registered kind is never masked by another class's cached entry.
    a = NodeRegistry.get("chunker", "fixed_size")
    b = NodeRegistry.get("chunker", "semantic")

    assert a.describe().kind == "fixed_size"
    assert b.describe().kind == "semantic"
    assert a.describe() is a.describe()
    assert a.describe() is not b.describe()
