# ====== Code Summary ======
# Structure guard of the DocumentApi split (R-09): every unit of ``apis/documents/`` stays within
# the 400-line budget, and the ``DocumentApi`` facade delegates each public method to exactly one
# split class (same callable, so SQL and behaviour are the ones the characterization goldens pin).

# ====== Standard Library Imports ======
import inspect
from pathlib import Path

# ====== Third-Party Library Imports ======
import pytest

# ====== Internal Project Imports ======
from shared_libs.services.db.postgresql.apis import documents
from shared_libs.services.db.postgresql.apis.document_api import DocumentApi

MAX_LINES = 400
DOCUMENTS_DIR = Path(documents.__file__).parent
SPLIT_CLASSES = [
    documents.DocumentRowApi,
    documents.DocumentMetadataApi,
    documents.DocumentPageApi,
]


@pytest.mark.parametrize("path", sorted(DOCUMENTS_DIR.glob("*.py")), ids=lambda p: p.name)
def test_unit_stays_within_line_budget(path: Path) -> None:
    """No unit of apis/documents/ grows past the 400-line budget."""
    assert len(path.read_text().splitlines()) <= MAX_LINES


def test_every_public_method_is_owned_by_exactly_one_split_class() -> None:
    """Each DocumentApi method resolves to one split class's method."""
    own = {
        name for name, _ in inspect.getmembers(DocumentApi, callable) if not name.startswith("__")
    }
    owners: dict[str, list[str]] = {}
    for cls in SPLIT_CLASSES:
        for name, _ in inspect.getmembers(cls, callable):
            if not name.startswith("__"):
                owners.setdefault(name, []).append(cls.__name__)
    # Every public method is exposed; private helpers only as far as callers use them.
    assert {n for n in owners if not n.startswith("_")} <= own
    assert own <= set(owners)
    assert all(len(classes) == 1 for classes in owners.values())
    for name in own:
        assert getattr(DocumentApi, name) == getattr(getattr(documents, owners[name][0]), name)


def test_document_api_stays_static_only() -> None:
    """The facade keeps the original no-instantiation guard."""
    with pytest.raises(TypeError):
        DocumentApi()
