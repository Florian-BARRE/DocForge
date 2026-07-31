# ====== Code Summary ======
# QASPER loader for the RAG benchmark. QASPER is QA over FULL scientific papers — each "document" is
# a long, explicitly SECTIONED paper (section_name + paragraphs), and every question ships the gold
# EVIDENCE paragraph(s) that answer it. That is exactly what exercises the structure-aware chunker:
# a paper is ingested, split along its section tree, and we measure whether the retrieved chunk
# COVERS the gold evidence. Papers are pulled page-by-page from the HuggingFace datasets-server
# `/rows` HTTP API (no `datasets` dependency) and cached under the gitignored data/ dir.

# ====== Standard Library Imports ======
import html
import json
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

_ROWS_URL = "https://datasets-server.huggingface.co/rows"
_DATASET = "allenai/qasper"
_CONFIG = "qasper"
_CACHE = Path(__file__).parent / "data" / "qasper_validation_rows.json"

# QASPER marks table/figure-only evidence with this sentinel — not retrievable text, so skipped.
_FLOAT_MARKER = "FLOAT SELECTED"


@dataclass(frozen=True)
class Question:
    """One QASPER question and its gold evidence passages (text-only, non-empty)."""

    question: str
    evidences: list[str]


@dataclass(frozen=True)
class Paper:
    """One QASPER paper — a long sectioned document plus its answerable questions."""

    paper_id: str
    title: str
    sections: list[tuple[str, list[str]]]  # (section_name, paragraphs)
    questions: list[Question] = field(default_factory=list)

    def to_html(self) -> str:
        """Render the paper as structured HTML (h1 title, h2 per section, p per paragraph).

        The explicit headings are what let the parser + structure-aware chunker cut along sections.
        """
        parts = [
            f"<!doctype html><html><head><title>{html.escape(self.title)}</title></head><body>"
        ]
        parts.append(f"<h1>{html.escape(self.title)}</h1>")
        for name, paragraphs in self.sections:
            if name and name.strip():
                parts.append(f"<h2>{html.escape(name.strip())}</h2>")
            for paragraph in paragraphs:
                if paragraph and paragraph.strip():
                    parts.append(f"<p>{html.escape(paragraph.strip())}</p>")
        parts.append("</body></html>")
        return "\n".join(parts)


def _fetch_rows(offset: int, length: int) -> list[dict]:
    """One page of QASPER validation rows from the datasets-server API (retried on transient error)."""
    url = (
        f"{_ROWS_URL}?dataset={_DATASET}&config={_CONFIG}&split=validation"
        f"&offset={offset}&length={length}"
    )
    for attempt in range(4):
        try:
            with urllib.request.urlopen(url, timeout=30) as response:
                return json.loads(response.read())["rows"]
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError):
            if attempt == 3:
                raise
            time.sleep(2 * (attempt + 1))
    return []


def _cached_rows(limit: int) -> list[dict]:
    """The first ``limit`` validation rows — served from the on-disk cache, filled from the API."""
    cached: list[dict] = []
    if _CACHE.exists():
        cached = json.loads(_CACHE.read_text())
    while len(cached) < limit:
        page = _fetch_rows(len(cached), min(100, limit - len(cached)))
        if not page:
            break
        cached.extend(row["row"] for row in page)
        _CACHE.parent.mkdir(parents=True, exist_ok=True)
        _CACHE.write_text(json.dumps(cached))
    return cached[:limit]


def _questions_from_row(row: dict) -> list[Question]:
    """Extract answerable questions with usable text evidence from a QASPER row."""
    qas = row.get("qas") or {}
    questions = qas.get("question") or []
    answers = qas.get("answers") or []
    out: list[Question] = []
    for index, text in enumerate(questions):
        evidences: list[str] = []
        annotations = answers[index]["answer"] if index < len(answers) else []
        for annotation in annotations:
            if annotation.get("unanswerable"):
                continue
            for passage in annotation.get("evidence") or []:
                if passage and _FLOAT_MARKER not in passage and len(passage.split()) >= 5:
                    evidences.append(passage.strip())
        # De-duplicate evidence passages while preserving order; a question needs at least one.
        deduped = list(dict.fromkeys(evidences))
        if text and deduped:
            out.append(Question(question=text.strip(), evidences=deduped))
    return out


def load_papers(limit: int) -> list[Paper]:
    """
    Load the first ``limit`` QASPER validation papers (cached), each with its answerable questions.

    Args:
        limit (int): Number of papers to load (a slice — the full split is ~281 papers).

    Returns:
        list[Paper]: Papers carrying sections + questions-with-evidence (papers with no answerable,
            text-evidence question are dropped, so every returned paper contributes to the score).
    """
    papers: list[Paper] = []
    for row in _cached_rows(limit):
        full_text = row.get("full_text") or {}
        names = full_text.get("section_name") or []
        paragraph_groups = full_text.get("paragraphs") or []
        sections = [
            (names[i] if i < len(names) else "", paragraph_groups[i])
            for i in range(len(paragraph_groups))
        ]
        questions = _questions_from_row(row)
        if sections and questions:
            papers.append(
                Paper(
                    paper_id=str(row.get("id") or f"paper_{len(papers)}"),
                    title=(row.get("title") or "Untitled").strip(),
                    sections=sections,
                    questions=questions,
                )
            )
    return papers


__all__ = ["Question", "Paper", "load_papers"]
