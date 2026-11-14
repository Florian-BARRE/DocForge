# ====== Code Summary ======
# Characterization of the statements DocumentApi sends to the database TODAY (safety net for the
# data-layer refactoring campaign). No database: each public method runs against a RecordingSession
# with fixed arguments and the operations it records (compiled PostgreSQL statements, ORM get / add,
# attribute writes) are compared with the inline golden. The set of public method names is frozen
# too, so a split of DocumentApi cannot silently drop or rename one. Methods covered "name only" are
# listed in ``NAME_ONLY``.

# ====== Third-Party Library Imports ======
import pytest

# ====== Internal Project Imports ======
from shared_libs.services.db.postgresql.apis.document_api import DocumentApi

# ====== Local Project Imports ======
from .support.api_runner import ApiRunner, CallSpec
from .support.document_api_golden import DOCUMENT_API_GOLDEN
from .support.document_call_specs import DOCUMENT_SPECS, NAME_ONLY

#: The public surface of DocumentApi, frozen. Adding a method means adding it here AND a call spec.
FROZEN_PUBLIC_METHODS: frozenset[str] = frozenset(
    {
        "count_by_collections",
        "count_for_collection",
        "create",
        "delete",
        "delete_many",
        "delete_metadata",
        "finalize_done",
        "find",
        "flag_replay_failure",
        "get",
        "get_by_ids",
        "get_chunk_filterable_metadata",
        "get_filterable_metadata",
        "get_filterable_metadata_for_documents",
        "get_for_update",
        "get_metadata",
        "get_metadata_for_documents",
        "get_metadata_with_names",
        "get_pages",
        "get_searchable_metadata",
        "list_disabled_ids",
        "list_enabled_ids",
        "list_for_collection",
        "mark_processing",
        "replace_metadata",
        "replace_pages",
        "set_enabled",
        "set_enabled_many",
        "set_status",
        "touch",
        "update_facts",
        "update_metadata",
    }
)


def test_public_method_set_is_frozen() -> None:
    """DocumentApi exposes exactly the frozen public methods — nothing dropped, renamed or added."""
    assert set(ApiRunner.public_methods(DocumentApi)) == FROZEN_PUBLIC_METHODS


def test_every_public_method_has_a_call_spec_or_is_name_only() -> None:
    """Each public method is either exercised by a call spec or explicitly listed as name-only."""
    exercised = {spec.method for spec in DOCUMENT_SPECS}
    assert exercised | NAME_ONLY == FROZEN_PUBLIC_METHODS
    assert exercised.isdisjoint(NAME_ONLY)


def test_golden_and_call_specs_list_the_same_calls() -> None:
    """No golden entry is stale and no call spec lacks its golden."""
    assert set(DOCUMENT_API_GOLDEN) == {spec.key for spec in DOCUMENT_SPECS}


@pytest.mark.parametrize("spec", DOCUMENT_SPECS, ids=lambda spec: spec.key)
async def test_statements_match_the_golden(spec: CallSpec) -> None:
    """The operations a DocumentApi call records are exactly the golden ones."""
    assert await ApiRunner.trace(spec) == DOCUMENT_API_GOLDEN[spec.key]
