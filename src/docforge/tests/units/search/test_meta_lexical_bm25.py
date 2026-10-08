"""The bm25_local sparse encoder (A8): analysis (fold/stopwords/stem), determinism, the
"Passation before Exécution" ranking regression with an in-test IDF, the config-derived IDF vector
schema (all-or-none across the sparse vectors), the single-sparse-query routing of the target
resolver, and the rerank skip for metadata-only searches."""

import math

from qdrant_client import models

from backend.libs.search.target_resolver import TargetVectorResolver
from backend.libs.search.tuning import SearchTuning
from shared_libs.pipelines.nodes.embed.providers.bm25_local import Bm25Analyzer, Bm25Encoder
from shared_libs.public_models.embed import SparseVector, VectorLayout
from shared_libs.public_models.search import RERANK_FLAG, EncodedQuery, SearchTarget
from shared_libs.services.db.qdrant import QdrantVectorSchema, VectorNames


def _encode_value(text: str) -> SparseVector:
    """A metadata value through the bm25_local FIELD parameters (k1 1.2, b 0.75, ref length 8)."""
    return Bm25Encoder.encode_document(text, k1=1.2, b=0.75, reference_length=8)


def test_fold_strips_accents_and_ligatures() -> None:
    assert Bm25Analyzer.fold("Exécution des Marchés — Œuvre") == "execution des marches — oeuvre"


def test_stopwords_are_dropped_in_both_languages() -> None:
    assert Bm25Analyzer.tokens("Passation des marchés de la ville") == [
        "passation",
        "marches",
        "ville",
    ]
    assert Bm25Analyzer.tokens("The state of the art") == ["state", "art"]


def test_stemming_unites_inflections() -> None:
    assert Bm25Encoder.encode_query("marché").indices == (
        Bm25Encoder.encode_query("marchés").indices
    )
    assert Bm25Encoder.encode_query("markets").indices == (
        Bm25Encoder.encode_query("market").indices
    )


def test_encoding_is_deterministic_and_sorted() -> None:
    first = _encode_value("Passation des marchés publics")
    second = _encode_value("Passation des marchés publics")
    assert first == second
    assert first.indices == sorted(first.indices)
    assert all(0 <= index < 2**32 for index in first.indices)
    assert Bm25Encoder.term_id("march") == Bm25Encoder.term_id("march")


def test_stopword_only_query_encodes_to_empty() -> None:
    assert Bm25Encoder.encode_query("des de la").indices == []


def _bm25_scores(query: str, values: dict[str, str]) -> dict[str, float]:
    """Qdrant's IDF-modifier scoring, computed in-test: Σ q·idf(t)·tf_bm25(t, value)."""
    docs = {key: _encode_value(text) for key, text in values.items()}
    total = len(docs)
    q = Bm25Encoder.encode_query(query)
    scores = {}
    for key, vec in docs.items():
        weights = dict(zip(vec.indices, vec.values, strict=True))
        score = 0.0
        for index, q_value in zip(q.indices, q.values, strict=True):
            if index not in weights:
                continue
            df = sum(1 for other in docs.values() if index in other.indices)
            idf = math.log(1 + (total - df + 0.5) / (df + 0.5))
            score += q_value * idf * weights[index]
        scores[key] = score
    return scores


def test_passation_ranks_above_execution() -> None:
    """The A8 regression: 'passation des marchés' must rank the Passation document first."""
    scores = _bm25_scores(
        "passation des marchés",
        {"passation": "Passation des marchés", "execution": "Exécution des marchés"},
    )
    assert scores["passation"] > scores["execution"]


def test_bm25_layout_declares_idf_on_every_sparse_vector() -> None:
    layout = VectorLayout(sparse_idf=True)
    config = QdrantVectorSchema.sparse_config(["nom"], layout)
    meta = VectorNames.field_sparse("nom")
    assert config[meta].modifier == models.Modifier.IDF
    assert config[VectorNames.CONTENT_SPARSE].modifier == models.Modifier.IDF
    assert not QdrantVectorSchema.modifier_mismatch(config[meta], layout)
    assert QdrantVectorSchema.modifier_mismatch(models.SparseVectorParams(), layout)


def test_learned_sparse_layout_declares_no_idf() -> None:
    config = QdrantVectorSchema.sparse_config(["nom"], VectorLayout())
    assert all(params.modifier is None for params in config.values())
    idf = models.SparseVectorParams(modifier=models.Modifier.IDF)
    assert QdrantVectorSchema.modifier_mismatch(idf, VectorLayout())


def test_no_sparse_provider_declares_no_sparse_vector() -> None:
    assert QdrantVectorSchema.sparse_config(["nom"], VectorLayout(sparse=False)) == {}
    assert QdrantVectorSchema.dense_config(1024, ["nom"], VectorLayout(dense=False)) == {}


_SPARSE = Bm25Encoder.encode_query("passation des marchés")
_ENCODED = EncodedQuery(dense=[0.1], sparse=_SPARSE)
_TARGET = [SearchTarget(field="nom", lexical=True)]


def test_resolver_sends_the_one_sparse_query_to_every_lexical_target() -> None:
    targets = _TARGET + [SearchTarget(field="content", lexical=True)]
    _, sparse = TargetVectorResolver.resolve(_ENCODED, targets)
    assert sparse[VectorNames.field_sparse("nom")].indices == _SPARSE.indices
    assert sparse[VectorNames.CONTENT_SPARSE].indices == _SPARSE.indices


def test_resolver_skips_an_empty_sparse_query_and_reports_it_termless() -> None:
    empty = EncodedQuery(dense=[0.1], sparse=SparseVector())
    targets = _TARGET + [SearchTarget(field="content", semantic=True)]
    dense, sparse = TargetVectorResolver.resolve(empty, targets)
    assert sparse is None and VectorNames.CONTENT_DENSE in dense
    assert TargetVectorResolver.termless_lexical_fields(empty, targets) == ["nom"]


def test_rerank_skipped_for_metadata_only_targets() -> None:
    tuning = SearchTuning().for_targets(_TARGET)
    assert tuning.flags() == {RERANK_FLAG: False}


def test_rerank_kept_when_content_is_targeted_or_explicitly_required() -> None:
    mixed = _TARGET + [SearchTarget(field="content", semantic=True)]
    assert SearchTuning().for_targets(mixed).flags() == {}
    assert SearchTuning().for_targets(None).flags() == {}
    assert SearchTuning(rerank=True).for_targets(_TARGET).rerank is True
