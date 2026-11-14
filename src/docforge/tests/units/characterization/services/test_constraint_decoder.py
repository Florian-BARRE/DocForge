# ====== Code Summary ======
# Characterization of the "IntegrityError -> violated constraint name" decoders of the data layer
# (safety net for the shared ConstraintViolation brick). Five sites each recognise ONE constraint of a
# driver IntegrityError and nothing else:
#   - CollectionAliasFacade._is_pk_race            -> pk_collection_alias
#   - CollectionNameConflict.is_duplicate_name     -> uq_collection_name
#   - IdempotencyFacade._is_scope_conflict         -> uq_idempotency_key_scope
#   - IngestionAdmission._is_duplicate_document    -> uq_document_collection_id
#   - IngestionAdmission._is_active_job_conflict   -> uq_job_active_per_document
# asyncpg carries ``constraint_name`` on its native error, which SQLAlchemy's adapter nests as the
# wrapper's ``__cause__`` (``error.orig``); the decoders inspect both hops. A refactor must keep every
# (site, constraint) verdict — including the "no name at all" and "no orig" cases.

# ====== Standard Library Imports ======
from collections.abc import Callable

# ====== Third-Party Library Imports ======
import pytest
from sqlalchemy.exc import IntegrityError

# ====== Internal Project Imports ======
from shared_libs.services.db.facades.collection_alias_facade import CollectionAliasFacade
from shared_libs.services.db.facades.collection_name_conflict import CollectionNameConflict
from shared_libs.services.db.facades.idempotency_facade import IdempotencyFacade
from shared_libs.services.db.facades.ingestion.ingestion_admission import IngestionAdmission

#: site label -> (decoder, the one constraint name it must match)
DECODERS: dict[str, tuple[Callable[[IntegrityError], bool], str]] = {
    "alias_pk": (CollectionAliasFacade._is_pk_race, "pk_collection_alias"),
    "collection_name": (CollectionNameConflict.is_duplicate_name, "uq_collection_name"),
    "idempotency_scope": (IdempotencyFacade._is_scope_conflict, "uq_idempotency_key_scope"),
    "document_unique": (IngestionAdmission._is_duplicate_document, "uq_document_collection_id"),
    "active_job_index": (IngestionAdmission._is_active_job_conflict, "uq_job_active_per_document"),
}

#: every constraint name a decoder matches, plus names no decoder owns
ALL_NAMES = [name for _decoder, name in DECODERS.values()] + [
    "uq_job_active_rebuild_per_collection",
    "some_other_constraint",
]


class _Native(Exception):
    """Stands for asyncpg's native error: carries ``constraint_name``."""

    def __init__(self, constraint_name: str | None) -> None:
        super().__init__("native")
        self.constraint_name = constraint_name


def _nested(constraint_name: str | None) -> IntegrityError:
    """SQLAlchemy's asyncpg shape: ``orig`` (no name) whose ``__cause__`` is the native error."""
    adapter = Exception("adapter")
    adapter.__cause__ = _Native(constraint_name)
    return IntegrityError("INSERT", {}, adapter)


def _direct(constraint_name: str | None) -> IntegrityError:
    """``orig`` itself carries the name."""
    return IntegrityError("INSERT", {}, _Native(constraint_name))


@pytest.mark.parametrize("site", list(DECODERS))
@pytest.mark.parametrize("shape", [_nested, _direct], ids=["nested-cause", "direct-orig"])
def test_a_decoder_matches_only_its_own_constraint(
    site: str, shape: Callable[[str | None], IntegrityError]
) -> None:
    decoder, own = DECODERS[site]
    for name in ALL_NAMES:
        assert decoder(shape(name)) is (name == own), f"{site} vs {name} ({shape.__name__})"


@pytest.mark.parametrize("site", list(DECODERS))
def test_a_decoder_rejects_an_error_without_a_constraint_name(site: str) -> None:
    decoder, _own = DECODERS[site]
    assert decoder(_nested(None)) is False
    assert decoder(_direct(None)) is False
    assert decoder(IntegrityError("INSERT", {}, Exception("plain"))) is False
    assert decoder(IntegrityError("INSERT", {}, None)) is False  # type: ignore[arg-type]
