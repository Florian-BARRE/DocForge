"""A stopword-only query on a term-based sparse provider (bm25_local) leaves an EMPTY sparse query, so a
lexical target resolves to no vector (axes=none, []). The read port records THAT cause on the probe,
and the search response carries a hint naming the target — only for that cause (a query with a term,
a collection with no sparse axis, or a degraded dense axis records nothing). The route-level wiring is covered in tests/units/api/test_search_termless_hint.py.
"""

import asyncio
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock

from backend.libs.search import TermlessQueryHint
from backend.libs.search.probe import AXES_NONE, SearchRetrievalProbe
from backend.libs.search.read_port import CollectionReadPortImpl
from shared_libs.public_models.embed import SparseVector
from shared_libs.public_models.search import Candidate, EncodedQuery, SearchTarget

_NOM = SearchTarget(field="nom", semantic=False, lexical=True)
_EMPTY = SparseVector(indices=[], values=[])


def _port() -> tuple[CollectionReadPortImpl, AsyncMock]:
    hybrid_ids = AsyncMock(return_value=[("c1", 0.5)])
    search = SimpleNamespace(hybrid_ids=hybrid_ids)
    return CollectionReadPortImpl(SimpleNamespace(search=search), uuid.uuid4()), hybrid_ids


def _search(port: CollectionReadPortImpl, encoded: EncodedQuery, targets: list) -> list:
    return asyncio.run(port.hybrid_search(encoded, filters={}, limit=10, targets=targets))


def test_stopword_query_records_the_termless_lexical_target() -> None:
    port, hybrid_ids = _port()
    encoded = EncodedQuery(dense=[], sparse=_EMPTY, model="m")

    assert _search(port, encoded, [_NOM]) == []

    hybrid_ids.assert_not_awaited()
    assert port.probe.axes == [AXES_NONE]
    assert port.probe.termless_lexical_fields == ["nom"]
    hint = TermlessQueryHint.build(port.probe, "le la les")[0]
    assert hint.field == "nom" and hint.value == "le la les"
    assert "no searchable term for lexical target 'nom'" in hint.message


def test_query_with_a_term_records_nothing() -> None:
    port, _ = _port()
    encoded = EncodedQuery(dense=[], sparse=SparseVector(indices=[7], values=[1.0]), model="m")

    assert _search(port, encoded, [_NOM]) == [Candidate(chunk_id="c1", score=0.5, source="hybrid")]
    assert port.probe.termless_lexical_fields == []


def test_other_axes_none_causes_record_nothing() -> None:
    # A collection with no sparse axis (sparse None), and a degraded dense axis.
    port, _ = _port()
    no_sparse = EncodedQuery(dense=[], sparse=None, model="m")
    assert _search(port, no_sparse, [_NOM]) == []
    degraded = EncodedQuery(dense=[], model="m")
    assert _search(port, degraded, [SearchTarget(field="content", semantic=True)]) == []

    assert port.probe.termless_lexical_fields == []
    assert TermlessQueryHint.build(port.probe, "q") == []


def test_probe_dedups_termless_fields_across_calls() -> None:
    probe = SearchRetrievalProbe()
    probe.record_termless_lexical(["nom", "titre"])
    probe.record_termless_lexical(["nom"])
    assert probe.termless_lexical_fields == ["nom", "titre"]
