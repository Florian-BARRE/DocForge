"""ExplorerHelpers read-side mapping: the DTOs must surface each chunk's role + EFFECTIVE enabled
state and each document's enabled flag. The effective chunk state follows the single policy
(role_default_enabled) with the user's enabled_override winning when set. Pure attribute mapping,
so SimpleNamespace stands in for the ORM rows.
"""

import uuid
from types import SimpleNamespace

import pytest


@pytest.fixture
def helpers(fastapi_app):
    """ExplorerHelpers, imported only after the app fixture put app/ on sys.path."""
    from backend.routers.explorer.helpers import ExplorerHelpers  # noqa: PLC0415

    return ExplorerHelpers


def _chunk(
    *,
    role: str = "body",
    enabled_override: bool | None = None,
    heading_path: list[str] | None = None,
) -> SimpleNamespace:
    """A minimal chunk row carrying only what the explorer mapping reads."""
    return SimpleNamespace(
        id=uuid.uuid4(),
        chunk_index=0,
        text="body text",
        token_count=3,
        is_indexed=True,
        strategy="recursive",
        parent_id=None,
        role=role,
        enabled_override=enabled_override,
        heading_path=heading_path,
    )


def _document(*, enabled: bool = True) -> SimpleNamespace:
    """A minimal document row carrying only what the list/detail mapping reads."""
    return SimpleNamespace(
        id=uuid.uuid4(),
        collection_id=uuid.uuid4(),
        filename="f.pdf",
        format="pdf",
        mime_type="application/pdf",
        file_size=10,
        page_count=1,
        language="en",
        title="Title",
        source_kind="digital_born",
        status="done",
        source_hash="h",
        pdf_blob_hash=None,
        simhash=None,
        pipeline_version="v1",
        created_at=None,
        enabled=enabled,
    )


def test_body_chunk_reads_role_body_enabled_true(helpers) -> None:
    """A body chunk with no override defaults to searchable."""
    info = helpers.chunk(_chunk(role="body"), [], [], page=None)
    assert info.role == "body"
    assert info.enabled is True


def test_header_footer_chunk_without_override_reads_disabled(helpers) -> None:
    """A non-body role with no override defers to the role default (off)."""
    info = helpers.chunk(_chunk(role="header_footer"), [], [], page=None)
    assert info.role == "header_footer"
    assert info.enabled is False


def test_override_wins_over_role_default(helpers) -> None:
    """An explicit enabled_override=True beats a non-body role's disabled default."""
    info = helpers.chunk(_chunk(role="boilerplate", enabled_override=True), [], [], page=None)
    assert info.role == "boilerplate"
    assert info.enabled is True


def test_unknown_role_without_override_degrades_to_disabled(helpers) -> None:
    """An unknown stored role (forward-compat/legacy) must not 500 — it degrades to disabled."""
    info = helpers.chunk(_chunk(role="quantum_role"), [], [], page=None)
    assert info.role == "quantum_role"
    assert info.enabled is False


def test_unknown_role_still_honours_explicit_override(helpers) -> None:
    """An explicit override wins even when the stored role is unrecognized (no enum coercion path)."""
    info = helpers.chunk(_chunk(role="quantum_role", enabled_override=True), [], [], page=None)
    assert info.enabled is True


def test_chunk_surfaces_heading_path_and_resolved_page(helpers) -> None:
    """The chunk DTO carries the section breadcrumb + the primary block's page (search-hit parity)."""
    info = helpers.chunk(_chunk(heading_path=["Intro", "Scope"]), ["b1", "b2"], [], page=4)
    assert info.heading_path == ["Intro", "Scope"]
    assert info.page == 4


def test_chunk_missing_heading_path_and_page_default_to_empty_and_none(helpers) -> None:
    """A chunk with no heading_path column value / no located block → [] and None."""
    info = helpers.chunk(_chunk(heading_path=None), [], [], page=None)
    assert info.heading_path == []
    assert info.page is None


def test_disabled_document_surfaces_enabled_false_in_list_and_detail(helpers) -> None:
    """The document-level enabled flag flows into both catalogue and detail DTOs."""
    document = _document(enabled=False)
    assert helpers.list_item(document).enabled is False
    assert helpers.detail(document, []).enabled is False
