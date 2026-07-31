# ====== Code Summary ======
# Unit tests for the synthetic regulatory corpus — pure generation, no stack, no network. They lock in
# the properties the benchmark relies on: documents are built deterministically, every clause is short
# enough to be coalesced under the default chunker (so default vs strict genuinely diverge), and every
# question points at exactly one clause that actually exists in its document.

# ====== Third-Party Library Imports ======
from tests.rag_eval.metrics import tokens
from tests.rag_eval.synthetic import load_regulatory_papers


def test_deterministic() -> None:
    """Two builds of the same size are byte-identical — reproducible benchmark runs."""
    assert load_regulatory_papers(6) == load_regulatory_papers(6)


def test_limit_is_respected_and_capped() -> None:
    """The slice honours the requested count and never exceeds the defined regulations."""
    assert len(load_regulatory_papers(3)) == 3
    assert len(load_regulatory_papers(999)) == 6


def test_every_question_evidence_is_a_real_clause() -> None:
    """Each question's gold evidence is verbatim one of its document's clause paragraphs."""
    for paper in load_regulatory_papers(6):
        clauses = {paragraph for _, paragraphs in paper.sections for paragraph in paragraphs}
        for question in paper.questions:
            assert question.evidences, "every question must carry evidence"
            assert set(question.evidences) <= clauses


def test_clauses_are_short_enough_to_coalesce() -> None:
    """Every clause sits well under the default min_tokens=64 — the reason this corpus tests chunking."""
    for paper in load_regulatory_papers(6):
        for _, paragraphs in paper.sections:
            for paragraph in paragraphs:
                assert len(tokens(paragraph)) < 64


def test_same_topic_diverges_across_documents() -> None:
    """The first-topic clause differs between two regulations — cross-document disambiguation is real."""
    papers = load_regulatory_papers(6)
    first_clause = [paper.sections[0][1][0] for paper in papers]
    assert len(set(first_clause)) > 1
