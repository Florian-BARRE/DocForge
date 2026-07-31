# ====== Code Summary ======
# A synthetic REGULATORY corpus for the RAG benchmark — the counterpart to QASPER. Where QASPER papers
# have big prose sections (so the chunker's min_tokens coalescing almost never fires), a regulation is
# a stack of MANY SHORT clauses: one article = one ~20-token rule. That is exactly the shape that makes
# the structure-aware chunker's granularity knob matter — under the default (min_tokens=64) a handful of
# neighbouring clauses are coalesced into one chunk, under strict (min_tokens=0) every clause stays its
# own chunk. Same topics recur across several regulations with DIFFERENT values, so a query must resolve
# to the right document's clause (the cross-file disambiguation a real regulatory RAG faces). The corpus
# is fully deterministic (index-driven, no randomness) and reuses the qasper `Paper`/`Question` types, so
# the whole harness runs it unchanged. Zero network, zero API cost.

# ====== Standard Library Imports ======
from tests.rag_eval.qasper import Paper, Question

# The regulations. Each is one document; the same clause topics recur in every one with different values.
_REGULATIONS = [
    "Data Protection Charter",
    "Financial Disclosure Standard",
    "Clinical Trial Protocol",
    "Information Security Policy",
    "Procurement Compliance Code",
    "Cloud Services Agreement",
]

# One entry per clause topic: (topic, clause template, question template, per-document value pool).
# Templates keep each clause short (~15-30 tokens) so it sits well under min_tokens=64 and gets coalesced
# under the default config but not under strict. The value pool gives each regulation a distinct answer,
# so the gold evidence for a question is a single, unambiguous clause.
_CLAUSES: list[tuple[str, str, str, list[str]]] = [
    (
        "Data retention",
        "Personal data shall be retained for no longer than {v} months after account closure, "
        "after which every copy is irreversibly deleted.",
        "In the {reg}, how many months is personal data retained after account closure?",
        ["12", "18", "24", "36", "48", "60"],
    ),
    (
        "Breach notification",
        "A confirmed personal data breach shall be reported to the supervisory authority within {v} "
        "hours of its detection.",
        "In the {reg}, within how many hours must a confirmed data breach be reported to the authority?",
        ["24", "36", "48", "72", "96", "12"],
    ),
    (
        "Encryption at rest",
        "All records stored at rest shall be encrypted with the {v} algorithm and the encryption keys "
        "shall be rotated quarterly.",
        "In the {reg}, which algorithm encrypts the records stored at rest?",
        [
            "AES-256-GCM",
            "ChaCha20-Poly1305",
            "AES-128-CBC",
            "Serpent-256",
            "Twofish-256",
            "Camellia-256",
        ],
    ),
    (
        "Consent withdrawal",
        "A data subject may withdraw consent at any time and processing based on that consent shall "
        "cease within {v} days of the request.",
        "In the {reg}, within how many days must processing stop after consent is withdrawn?",
        ["3", "5", "7", "10", "14", "30"],
    ),
    (
        "Subject access request",
        "The controller shall respond to a subject access request within {v} calendar days of receipt "
        "and without charge.",
        "In the {reg}, how many calendar days are allowed to respond to a subject access request?",
        ["15", "20", "30", "40", "45", "60"],
    ),
    (
        "Subprocessor approval",
        "The processor shall give the controller at least {v} days written notice before engaging any "
        "new subprocessor.",
        "In the {reg}, how many days of written notice are required before engaging a new subprocessor?",
        ["7", "14", "21", "28", "45", "90"],
    ),
    (
        "Audit rights",
        "The controller may audit the processor's compliance no more than {v} times per calendar year "
        "on reasonable notice.",
        "In the {reg}, how many times per calendar year may the controller audit the processor?",
        ["1", "2", "3", "4", "6", "12"],
    ),
    (
        "Data residency",
        "All production data shall be stored and processed exclusively within data centres located in "
        "{v}.",
        "In the {reg}, in which jurisdiction must all production data be stored?",
        ["Ireland", "Germany", "Switzerland", "Canada", "Singapore", "France"],
    ),
]

# A cross-reference tail is appended to some clauses (renvoi between articles) — the interlinked-document
# trait a regulatory RAG must handle. It never carries the answer, only tests that retrieval is not
# derailed by an internal pointer.
_XREF_TAIL = " This clause shall be read together with Article {other} of the {reg}."


def _clause_text(template: str, value: str, reg: str, topic_index: int, doc_index: int) -> str:
    """Instantiate one clause, appending a cross-reference tail on a deterministic third of clauses."""
    text = template.format(v=value)
    if (doc_index + topic_index) % 3 == 0:
        other = ((topic_index + 3) % len(_CLAUSES)) + 1
        text += _XREF_TAIL.format(other=other, reg=reg)
    return text


def load_regulatory_papers(limit: int) -> list[Paper]:
    """
    Build up to ``limit`` synthetic regulations, each a document of short single-clause articles.

    Args:
        limit (int): Number of regulations to build (capped at the number of defined regulations).

    Returns:
        list[Paper]: Papers whose sections are short clauses and whose questions each point at exactly
            one clause as gold evidence — the shape that makes chunk granularity measurable.
    """
    papers: list[Paper] = []
    for doc_index, reg in enumerate(_REGULATIONS[: max(0, limit)]):
        sections: list[tuple[str, list[str]]] = []
        questions: list[Question] = []
        for topic_index, (topic, clause, question, values) in enumerate(_CLAUSES):
            value = values[doc_index % len(values)]
            text = _clause_text(clause, value, reg, topic_index, doc_index)
            sections.append((f"Article {topic_index + 1} — {topic}", [text]))
            questions.append(Question(question=question.format(reg=reg), evidences=[text]))
        papers.append(
            Paper(
                paper_id=f"reg_{doc_index}_{reg.lower().replace(' ', '_')}",
                title=reg,
                sections=sections,
                questions=questions,
            )
        )
    return papers


__all__ = ["load_regulatory_papers"]
