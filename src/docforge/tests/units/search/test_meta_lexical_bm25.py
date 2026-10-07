"""The local metadata BM25 encoder (A8): analysis (fold/stopwords/stem), determinism, the
"Passation before Exécution" ranking regression with an in-test IDF, the IDF-declared vector schema,
the per-vector encoding routing of the target resolver (old collections keep the BGE query), and the
rerank skip for metadata-only searches."""

import math

from qdrant_client import models

from backend.libs.search.target_resolver import TargetVectorResolver
from backend.libs.search.tuning import SearchTuning
from shared_libs.pipelines.nodes.embed.lexical import MetaLexicalAnalyzer, MetaLexicalEncoder
from shared_libs.public_models.embed import SparseVector
from shared_libs.public_models.search import RERANK_FLAG, EncodedQuery, SearchTarget
from shared_libs.services.db.qdrant import QdrantVectorSchema, VectorNames


def test_fold_strips_accents_and_ligatures() -> None:
    assert (
        MetaLexicalAnalyzer.fold("Exécution des Marchés — Œuvre")
        == "execution des marches — oeuvre"
    )


def test_stopwords_are_dropped_in_both_languages() -> None:
    assert MetaLexicalAnalyzer.tokens("Passation des marchés de la ville") == [
        "passation",
        "marches",
        "ville",
    ]
    assert MetaLexicalAnalyzer.tokens("The state of the art") == ["state", "art"]


def test_stemming_unites_inflections() -> None:
    assert MetaLexicalEncoder.encode_query("marché").indices == (
        MetaLexicalEncoder.encode_query("marchés").indices
    )
    assert MetaLexicalEncoder.encode_query("markets").indices == (
        MetaLexicalEncoder.encode_query("market").indices
    )


def test_encoding_is_deterministic_and_sorted() -> None:
    first = MetaLexicalEncoder.encode_value("Passation des marchés publics")
    second = MetaLexicalEncoder.encode_value("Passation des marchés publics")
    assert first == second
    assert first.indices == sorted(first.indices)
    assert all(0 <= index < 2**32 for index in first.indices)
    assert MetaLexicalEncoder.term_id("march") == MetaLexicalEncoder.term_id("march")


def test_stopword_only_query_encodes_to_empty() -> None:
    assert MetaLexicalEncoder.encode_query("des de la").indices == []


def _bm25_scores(query: str, values: dict[str, str]) -> dict[str, float]:
    """Qdrant's IDF-modifier scoring, computed in-test: Σ q·idf(t)·tf_bm25(t, value)."""
    docs = {key: MetaLexicalEncoder.encode_value(text) for key, text in values.items()}
    total = len(docs)
    q = MetaLexicalEncoder.encode_query(query)
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


def test_meta_sparse_vectors_are_idf_declared_content_is_not() -> None:
    config = QdrantVectorSchema.sparse_config(["nom"])
    meta = VectorNames.field_sparse("nom")
    assert config[meta].modifier == models.Modifier.IDF
    assert config[VectorNames.CONTENT_SPARSE].modifier is None
    assert QdrantVectorSchema.is_bm25_meta(meta, config[meta])
    assert not QdrantVectorSchema.is_bm25_meta(meta, models.SparseVectorParams())
    assert not QdrantVectorSchema.is_bm25_meta(
        VectorNames.CONTENT_SPARSE, models.SparseVectorParams(modifier=models.Modifier.IDF)
    )


_BGE = SparseVector(indices=[1, 2], values=[0.3, 0.4])
_BM25 = MetaLexicalEncoder.encode_query("passation des marchés")
_ENCODED = EncodedQuery(dense=[0.1], sparse=_BGE, meta_sparse=_BM25)
_TARGET = [SearchTarget(field="nom", lexical=True)]


def test_resolver_sends_bm25_query_to_a_bm25_vector() -> None:
    name = VectorNames.field_sparse("nom")
    _, sparse = TargetVectorResolver.resolve(_ENCODED, _TARGET, {name})
    assert sparse[name].indices == _BM25.indices


def test_resolver_keeps_the_bge_query_on_an_old_collection() -> None:
    """A legacy (non-IDF) meta vector holds BGE weights → it is queried with the BGE sparse."""
    _, sparse = TargetVectorResolver.resolve(_ENCODED, _TARGET, set())
    assert sparse[VectorNames.field_sparse("nom")].indices == _BGE.indices


def test_resolver_content_sparse_is_always_the_embedder_query() -> None:
    targets = [SearchTarget(field="content", lexical=True)]
    _, sparse = TargetVectorResolver.resolve(_ENCODED, targets, {VectorNames.field_sparse("nom")})
    assert sparse[VectorNames.CONTENT_SPARSE].indices == _BGE.indices


def test_rerank_skipped_for_metadata_only_targets() -> None:
    tuning = SearchTuning().for_targets(_TARGET)
    assert tuning.flags() == {RERANK_FLAG: False}


def test_rerank_kept_when_content_is_targeted_or_explicitly_required() -> None:
    mixed = _TARGET + [SearchTarget(field="content", semantic=True)]
    assert SearchTuning().for_targets(mixed).flags() == {}
    assert SearchTuning().for_targets(None).flags() == {}
    assert SearchTuning(rerank=True).for_targets(_TARGET).rerank is True
