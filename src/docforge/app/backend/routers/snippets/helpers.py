# ====== Code Summary ======
# SnippetHelpers — the pure (store-free) logic behind the snippet routes: SHAPING a collection slice
# into a secret-masked, versioned snippet wrapper (export), and UNWRAPPING an inbound snippet back to
# its raw body after validating its format version + kind (import). Secret masking reuses the ONE
# shared blob_secrets definition and the collection read's public-pipeline / field-spec mappers, so a
# snippet can never drift from the collection read on what a secret is or how a field is shaped.

# ====== Third-Party Library Imports ======
from fastapi import HTTPException
from loggerplusplus import loggerplusplus

# ====== Internal Project Imports ======
from shared_libs.pipelines.blob_secrets import redact_blob_secrets
from shared_libs.services.db.postgresql.tables import Collection, MetadataField

# ====== Local Project Imports ======
from ..collections.helpers import CollectionHelpers
from ..collections.models import FieldSpecModel
from .models import (
    CURRENT_SNIPPET_VERSION,
    SUPPORTED_SNIPPET_VERSIONS,
    CollectionSnippet,
    SnippetKind,
    is_supported_snippet_version,
)


class SnippetHelpers:
    """Static helpers: build a config-slice snippet (export) and unwrap one (import)."""

    logger = loggerplusplus.bind(identifier="SnippetHelpers")

    def __new__(cls, *args: object, **kwargs: object) -> None:
        raise TypeError("SnippetHelpers is a static-only class and cannot be instantiated.")

    # -------------------- export --------------------
    @classmethod
    def build(
        cls,
        kind: SnippetKind,
        collection: Collection,
        schema: list[MetadataField],
        docforge_version: str,
    ) -> CollectionSnippet:
        """
        Shape one of a collection's config slices into a portable, secret-masked snippet wrapper.

        Args:
            kind (SnippetKind): Which slice to export (pipeline / search / schema).
            collection (Collection): The source collection row.
            schema (list[MetadataField]): The collection's metadata schema (used for ``schema``).
            docforge_version (str): The producing build's version (stamped for provenance).

        Returns:
            CollectionSnippet: The versioned, masked snippet ready to serialise.
        """
        # 1. Build the kind-specific body (blobs masked via the shared secret walker).
        if kind == "pipeline":
            body = redact_blob_secrets(CollectionHelpers.public_pipeline(collection.pipeline)) or {}
        elif kind == "search":
            body = redact_blob_secrets(collection.search) or {}
        else:  # schema
            body = {
                "fields": [
                    spec.model_dump(mode="json")
                    for spec in CollectionHelpers.to_field_specs(schema)
                ]
            }

        # 2. Wrap it with the current format version + provenance stamp.
        return CollectionSnippet(
            kind=kind,
            format_version=CURRENT_SNIPPET_VERSION,
            docforge_version=docforge_version,
            body=body,
        )

    # -------------------- import --------------------
    @classmethod
    def unwrap(cls, snippet: CollectionSnippet, expected_kind: SnippetKind) -> dict:
        """
        Validate an inbound snippet's version + kind and return its raw body.

        Args:
            snippet (CollectionSnippet): The inbound snippet wrapper.
            expected_kind (SnippetKind): The kind the target endpoint applies.

        Returns:
            dict: The snippet body (blob dict, or {'fields': [...]} for a schema snippet).

        Raises:
            HTTPException: 422 when the format version is unsupported or the kind mismatches.
        """
        # 1. Reject a snippet this build cannot read (a future format version).
        if not is_supported_snippet_version(snippet.format_version):
            raise HTTPException(
                status_code=422,
                detail=f"Unsupported snippet format_version {snippet.format_version} "
                f"(this build reads: {sorted(SUPPORTED_SNIPPET_VERSIONS)}).",
            )
        # 2. The kind must match the endpoint — a search snippet cannot be applied as a pipeline.
        if snippet.kind != expected_kind:
            raise HTTPException(
                status_code=422,
                detail=f"Snippet kind '{snippet.kind}' cannot be applied here "
                f"(expected a '{expected_kind}' snippet).",
            )
        return snippet.body

    @classmethod
    def body_to_fields(cls, body: dict) -> list[FieldSpecModel]:
        """
        Parse a schema snippet's body into typed field specs (fail-fast on a malformed body).

        Args:
            body (dict): The schema snippet body — must carry a ``fields`` list.

        Returns:
            list[FieldSpecModel]: The parsed, per-field specs (validated by the model).

        Raises:
            HTTPException: 422 when ``fields`` is missing/not a list, or a field spec is malformed.
        """
        # 1. The body must carry a fields list — anything else is a malformed schema snippet.
        fields = body.get("fields")
        if not isinstance(fields, list):
            raise HTTPException(
                status_code=422,
                detail="A schema snippet body must carry a 'fields' list.",
            )
        # 2. Parse each entry through the field-spec model (extra='forbid' → a typo is a clean 422).
        try:
            return [FieldSpecModel.model_validate(entry) for entry in fields]
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=f"Malformed schema snippet field: {exc}")


__all__ = ["SnippetHelpers"]
