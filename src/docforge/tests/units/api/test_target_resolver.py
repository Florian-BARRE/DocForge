"""TargetVectorResolver.resolve — pure static mapping from SearchTarget selections to the named
query-vector dicts a store search consumes. No store, no mocks: only EncodedQuery/SearchTarget in,
a (dense, sparse) tuple out. ``from backend...`` deferred until fastapi_app registered app/ on
sys.path (target_resolver.py lives under app/backend/libs/search)."""

import pytest


def _encoded(dense=None, sparse=None):
    from shared_libs.public_models.embed import SparseVector
    from shared_libs.public_models.search import EncodedQuery

    return EncodedQuery(
        dense=dense if dense is not None else [0.1, 0.2],
        sparse=SparseVector(indices=[1, 2], values=[0.5, 0.5]) if sparse else None,
        model="fake",
    )


def _target(field="content", semantic=False, lexical=False):
    from shared_libs.public_models.search import SearchTarget

    return SearchTarget(field=field, semantic=semantic, lexical=lexical)


def test_content_semantic_resolves_to_content_dense(fastapi_app) -> None:
    from backend.libs.search.target_resolver import TargetVectorResolver  # noqa: PLC0415
    from shared_libs.services.db.qdrant import VectorNames  # noqa: PLC0415

    encoded = _encoded()
    dense, sparse = TargetVectorResolver.resolve(encoded, [_target(semantic=True)])

    assert dense == {VectorNames.CONTENT_DENSE: encoded.dense}
    assert sparse is None


def test_metadata_semantic_resolves_to_field_dense(fastapi_app) -> None:
    from backend.libs.search.target_resolver import TargetVectorResolver  # noqa: PLC0415
    from shared_libs.services.db.qdrant import VectorNames  # noqa: PLC0415

    encoded = _encoded()
    dense, sparse = TargetVectorResolver.resolve(encoded, [_target(field="author", semantic=True)])

    assert dense == {VectorNames.field_dense("author"): encoded.dense}
    assert sparse is None


def test_content_lexical_resolves_to_content_sparse(fastapi_app) -> None:
    from backend.libs.search.target_resolver import TargetVectorResolver  # noqa: PLC0415
    from shared_libs.services.db.qdrant import VectorNames  # noqa: PLC0415

    encoded = _encoded(sparse=True)
    dense, sparse = TargetVectorResolver.resolve(encoded, [_target(lexical=True)])

    assert dense == {}
    assert sparse.keys() == {VectorNames.CONTENT_SPARSE}
    assert sparse[VectorNames.CONTENT_SPARSE].indices == encoded.sparse.indices
    assert sparse[VectorNames.CONTENT_SPARSE].values == encoded.sparse.values


def test_metadata_lexical_resolves_to_field_sparse(fastapi_app) -> None:
    from backend.libs.search.target_resolver import TargetVectorResolver  # noqa: PLC0415
    from shared_libs.services.db.qdrant import VectorNames  # noqa: PLC0415

    encoded = _encoded(sparse=True)
    dense, sparse = TargetVectorResolver.resolve(encoded, [_target(field="tags", lexical=True)])

    assert dense == {}
    name = VectorNames.field_sparse("tags")
    assert sparse.keys() == {name}
    assert sparse[name].indices == encoded.sparse.indices
    assert sparse[name].values == encoded.sparse.values


def test_lexical_only_with_no_sparse_vector_resolves_to_no_vector_raises(fastapi_app) -> None:
    """A lexical-only target set with encoded.sparse is None resolves to no queryable vector."""
    from backend.libs.search.target_resolver import TargetVectorResolver  # noqa: PLC0415

    encoded = _encoded(sparse=False)
    with pytest.raises(ValueError):
        TargetVectorResolver.resolve(encoded, [_target(lexical=True)])
