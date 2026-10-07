# ====== Code Summary ======
# CollectionHelpers — the pure (store-free) logic behind the collections routes, kept out of
# router.py so the routes stay orchestration. It owns: the row → UI-contract mapping (the single
# secret-masking boundary), the metadata-field guards (mirror of the DB CHECK constraints), the
# search-blob shape guard, and the metadata-field row building. Pipeline-blob concerns (preset,
# canonicalize, embed vector-space) live in blob_helpers.py.

# ====== Standard Library Imports ======
from collections.abc import Callable

# ====== Third-Party Library Imports ======
from fastapi import HTTPException
from loggerplusplus import loggerplusplus

# ====== Internal Project Imports ======
from shared_libs.pipelines.blob_secrets import has_blob_secrets, redact_blob_secrets
from shared_libs.pipelines.ingest import BlobNormalizer, FormatProbeHelpers
from shared_libs.public_models import FieldOrigin, FieldScope, FieldType, TextSanitizer
from shared_libs.services.db.postgresql.tables import Collection, MetadataField
from shared_libs.services.db.qdrant import RESERVED_PAYLOAD_KEYS

# ====== Local Project Imports ======
from ...libs.estimate import EstimateOverrides
from ...libs.health import CollectionHealthSummary
from ...libs.schema_ops import SchemaDiff
from ...utils.search_blob_validation import SearchBlobValidator
from .models import (
    CollectionContractModel,
    CollectionContractSchemaResponse,
    CollectionListItem,
    CollectionModel,
    FieldSpecModel,
    UpdateCollectionResponse,
)

# Payload keys the chunk point owns for its own machinery (id, ordinal, enable-filter). A
# filterable field is denormalised onto the point by NAME, so a field sharing one of these would
# overwrite it and corrupt search/deletion — reserved regardless of the current filterable flag,
# which can be toggled on later.
# "content" is the search-target sentinel for the chunk body; a metadata field of that name would
# be un-targetable (it always resolves to the body vectors), so it is reserved alongside the
# point's own payload keys (RESERVED_PAYLOAD_KEYS — the single source, shared with the writers).
_RESERVED_FIELD_NAMES = RESERVED_PAYLOAD_KEYS | {"content"}


class CollectionHelpers:
    """Static, store-free helpers for the collections routes (mapping, guards, schema rows)."""

    logger = loggerplusplus.bind(identifier="CollectionHelpers")

    def __new__(cls, *args: object, **kwargs: object) -> None:
        raise TypeError("CollectionHelpers is a static-only class and cannot be instantiated.")

    # -------------------- mapping --------------------
    @staticmethod
    def public_pipeline(pipeline: dict | None) -> dict | None:
        """Strip the internal version stamp so the API exposes a clean, editable graph blob.

        The stamp is a STORAGE-side optimization (fast-path detection); the ``GroupNodeBlob`` the UI
        posts back to the stage endpoints forbids extra keys, so it must never see the reserved key.
        """
        if not isinstance(pipeline, dict):
            return pipeline
        return {key: value for key, value in pipeline.items() if key != BlobNormalizer.STAMP_KEY}

    @classmethod
    def __base_payload(
        cls,
        collection: Collection,
        fields: list[MetadataField],
        *,
        mask: Callable[[dict | None], dict | None],
    ) -> dict:
        """Build the shared scalar/blob/field payload every collection read model is composed from.

        The ONE place the ORM row is mapped to the UI contract's kwargs, so the single-collection read
        (``to_model``) and the fleet-list row (``to_list_item``) can never drift on a field. ``mask``
        is the provider-secret masker applied to BOTH config blobs: the full deepcopy redactor on the
        single read, the deepcopy-skipping variant on the list (see ``_mask_for_list``).

        Args:
            collection (Collection): The contract row.
            fields (list[MetadataField]): The collection's metadata schema rows.
            mask (Callable): The secret-masking function applied to the pipeline + search blobs.

        Returns:
            dict: The keyword arguments shared by ``CollectionModel`` and ``CollectionListItem``.
        """
        return dict(
            id=str(collection.id),
            name=collection.name,
            supported_formats=list(collection.supported_formats),
            tags=list(collection.tags),
            max_file_size_bytes=collection.max_file_size_bytes,
            job_timeout_seconds=collection.job_timeout_seconds,
            trace_verbosity=getattr(collection, "trace_verbosity", None) or "shape",
            needs_reindex=collection.needs_reindex,
            created_at=collection.created_at,
            pipeline=mask(cls.public_pipeline(collection.pipeline)),
            search=mask(collection.search),
            fields=cls.to_field_specs(fields),
            title_field=getattr(collection, "title_field", None),
            estimate_overrides=cls.__estimate_overrides(collection),
        )

    @staticmethod
    def _mask_for_list(blob: dict | None) -> dict | None:
        """Mask a config blob for the fleet list, skipping the deepcopy when it carries no secret.

        ``redact_blob_secrets`` ALWAYS deep-copies before masking (the safe single-read boundary). On
        the fleet list that copy runs twice per collection, overwhelmingly for blobs with NO provider
        secret (the stock in-stack pipeline). So this pays the copy only when a real secret is present
        and otherwise serialises the stored blob as-is — the masked result would be byte-identical.
        """
        return redact_blob_secrets(blob) if has_blob_secrets(blob) else blob

    @classmethod
    def to_model(
        cls,
        collection: Collection,
        fields: list[MetadataField],
        missing_vectors: list[str] | None = None,
        aliases: list[str] | None = None,
    ) -> CollectionModel:
        """Map the rows to the UI contract (shared by every single-collection read path).

        Provider secrets (api_key on every provider node of the pipeline AND search blobs) are masked
        here — the ONE serialisation boundary every read path funnels through — so a live key is never
        echoed to a client. The stored blobs keep the real keys; only this outbound copy is masked.
        ``missing_vectors`` is the store-side gap the caller read and ``aliases`` the collection
        aliases targeting it (None = not computed on this path).
        """
        return CollectionModel(
            **cls.__base_payload(collection, fields, mask=redact_blob_secrets),
            missing_vectors=missing_vectors,
            aliases=aliases,
        )

    @classmethod
    def to_list_item(
        cls,
        collection: Collection,
        fields: list[MetadataField],
        health: CollectionHealthSummary,
    ) -> CollectionListItem:
        """Map a collection + its schema + health summary straight to a fleet-list row.

        Built DIRECTLY (not ``to_model(...).model_dump()`` re-splat into the subclass, which paid two
        Pydantic validations + a dict dump per row). Masking uses the deepcopy-skipping ``_mask_for_list``
        since the list overwhelmingly renders secret-free stock blobs.
        """
        return CollectionListItem(
            **cls.__base_payload(collection, fields, mask=cls._mask_for_list),
            health=health,
        )

    @classmethod
    def to_update_response(
        cls,
        collection: Collection,
        fields: list[MetadataField],
        schema: object | None,
        dry_run: bool,
        missing: list[tuple[str, str]] | None = None,
    ) -> UpdateCollectionResponse:
        """Map a PATCHed (or, under dry_run, untouched) collection + its schema diff to the response.

        The diff's ``reindex_required_fields`` is made accurate against the vector store: every field
        whose named vector the store lacks (``missing``, computed over the post-PATCH schema — the
        target schema under dry_run) is added, so a field the planner judged unchanged but whose vector
        was never declared is still reported.

        Args:
            collection (Collection): The collection row to render.
            fields (list[MetadataField]): Its stored schema rows.
            schema (object | None): The resolved schema patch (carries ``diff``), None when the PATCH
                did not touch the schema (→ an empty diff).
            dry_run (bool): Whether nothing was written.
            missing (list[tuple[str, str]] | None): The ``(field, vector)`` pairs the store lacks.

        Returns:
            UpdateCollectionResponse: The contract + ``schema_diff`` + ``dry_run`` + ``missing_vectors``.
        """
        # 1. Union the planner's reindex verdict with the store truth (never under-reports).
        diff = (getattr(schema, "diff", None) or SchemaDiff()).model_copy(deep=True)
        gaps = missing or []
        diff.reindex_required_fields = sorted(
            set(diff.reindex_required_fields) | {field for field, _ in gaps}
        )
        return UpdateCollectionResponse(
            **cls.__base_payload(collection, fields, mask=redact_blob_secrets),
            missing_vectors=sorted(vector for _, vector in gaps),
            schema_diff=diff,
            dry_run=dry_run,
        )

    @staticmethod
    def to_field_specs(fields: list[MetadataField]) -> list[FieldSpecModel]:
        """Map metadata field rows to their UI ``FieldSpecModel`` (shared by read + snippet export)."""
        return [
            FieldSpecModel(
                field_name=row.field_name,
                field_type=row.field_type,
                required=row.required,
                filterable=row.filterable,
                lexical=row.lexical,
                semantic=row.semantic,
                enum_values=row.enum_values,
                origin=row.origin,
                scope=row.scope,
                description=getattr(row, "description", None),
            )
            for row in fields
        ]

    @staticmethod
    def __estimate_overrides(collection: Collection) -> EstimateOverrides | None:
        """Validate the stored partial estimate overrides to the typed model (None when unset).

        Rates carry no secret, so no masking is applied — the overrides round-trip verbatim.
        """
        stored = getattr(collection, "estimate_overrides", None)
        return EstimateOverrides.model_validate(stored) if stored else None

    # -------------------- discovery --------------------
    @staticmethod
    def contract_schema() -> CollectionContractSchemaResponse:
        """Build the collection-contract discovery payload — the full vocabulary, no guessing.

        Every part is serialized from the SAME canonical server source it validates against, so the
        discovery surface can never drift from what an upload/create actually accepts:
        - ``config_schema``: the identity/limits scalar contract (``CollectionContractModel``);
        - ``field_schema``: one metadata ``FieldSpecModel`` (its ``$defs`` carry the
          ``field_type``/``origin``/``scope`` enums the scalar contract omits);
        - ``supported_format_tokens``: the pipeline's own accepted upload tokens.

        Returns:
            CollectionContractSchemaResponse: The schema-driven form + the field/format vocabulary.
        """
        return CollectionContractSchemaResponse(
            config_schema=CollectionContractModel.model_json_schema(),
            field_schema=FieldSpecModel.model_json_schema(),
            supported_format_tokens=FormatProbeHelpers.supported_format_tokens(),
        )

    # -------------------- validation --------------------
    @staticmethod
    def validate_fields(fields: list[FieldSpecModel]) -> None:
        """Schema-level guards with explicit 422s (mirror of the DB CHECK constraints)."""
        for spec in fields:
            # An enum field is a string constrained to enum_values; with none declared it constrains
            # nothing and the runtime coercion has no allowed set to check against — reject the empty
            # enum up front rather than store a field that can never validate a value.
            if spec.field_type == FieldType.ENUM and not spec.enum_values:
                raise HTTPException(
                    status_code=422,
                    detail=f"Field '{spec.field_name}': an enum field must declare a non-empty "
                    f"'enum_values' list.",
                )
            # Chunk-scope values are produced by the pipeline — a user cannot declare them
            # at upload, so chunk scope is reserved for GENERATED fields (DB CHECK mirrors this).
            if spec.scope == FieldScope.CHUNK and spec.origin != FieldOrigin.GENERATED:
                raise HTTPException(
                    status_code=422,
                    detail=f"Field '{spec.field_name}': chunk scope is reserved for generated "
                    f"fields — user-declared metadata is document-level.",
                )
            # A field name must never shadow a reserved chunk-payload key (it would overwrite it
            # when denormalised onto the point, breaking the enabled-filter or deletion-by-document).
            if spec.field_name in _RESERVED_FIELD_NAMES:
                raise HTTPException(
                    status_code=422,
                    detail=f"Field name '{spec.field_name}' is reserved — pick another name "
                    f"(reserved: {sorted(_RESERVED_FIELD_NAMES)}).",
                )
            # Chunk-scope lexical has no BM25 producer: its only producer is the embed node's
            # ``embed_lexical_fields`` path, which writes the EMBEDDER's learned sparse weights (BGE),
            # while a new meta_<slug>_bm25 vector is declared IDF and queried with the local BM25
            # encoder (the meta-vector facade, which IS BM25, is document-scope only). Accepting it would
            # mix encoders under one vector, so it is refused up front; the BGE path only still serves
            # older, pre-IDF collections.
            if spec.scope == FieldScope.CHUNK and spec.lexical:
                raise HTTPException(
                    status_code=422,
                    detail=f"Field '{spec.field_name}': chunk-scope lexical search is not supported "
                    f"(no BM25 producer for chunk metadata) — use semantic, or document scope.",
                )

    @staticmethod
    def document_scope_field_names(fields: list[FieldSpecModel] | list[MetadataField]) -> list[str]:
        """The sorted names of the document-scope fields — the only valid ``title_field`` choices."""
        return sorted(f.field_name for f in fields if f.scope == FieldScope.DOCUMENT)

    @classmethod
    def validate_title_field(
        cls, title_field: str | None, fields: list[FieldSpecModel] | list[MetadataField]
    ) -> None:
        """Guard a ``title_field`` against the schema it will live with (None = clear, always valid).

        A display title is ONE value per document, so only a document-scope field qualifies — a
        chunk-scope field has no single per-document value to show.

        Args:
            title_field (str | None): The requested title field name, or None to clear it.
            fields (list): The schema the collection will have once the write lands.

        Raises:
            HTTPException: 422 naming the valid choices when the name is not a document-scope field.
        """
        # 1. Clearing is always allowed.
        if title_field is None:
            return

        # 2. The name must be one of the schema's document-scope fields.
        choices = cls.document_scope_field_names(fields)
        if title_field not in choices:
            raise HTTPException(
                status_code=422,
                detail=f"title_field '{title_field}' is not a document-scope metadata field of this "
                f"collection — valid choices: {choices} (or null to clear).",
            )

    @staticmethod
    def validate_search_blob(search: dict) -> None:
        """Guard a non-empty search blob's shape and validate it as a genuine SEARCH graph.

        A new search blob is a search GRAPH blob. Only two shapes are valid: {} (the sentinel
        "use the stock default", handled by the caller) or a real topology carrying a "nodes" list.
        A non-empty dict WITHOUT "nodes" would be stored then silently ignored at read
        (__resolve_blob falls back to the default) — reject it up front. A real topology is
        validated not just structurally but as a genuine SEARCH pipeline (it must terminate on a
        SearchResult), so a non-search graph cannot be stored to 500 on every subsequent query.

        Args:
            search (dict): The healed, non-empty search blob to validate.

        Raises:
            HTTPException: 422 when the blob has no "nodes" list; validator errors for a non-search graph.
        """
        if "nodes" not in search:
            raise HTTPException(
                status_code=422,
                detail="collection.search must be empty ({} = stock default) or a search graph "
                "blob with a 'nodes' list.",
            )
        SearchBlobValidator.validate(search)

    # -------------------- schema rows --------------------
    @staticmethod
    def to_field_rows(fields: list[FieldSpecModel]) -> list[MetadataField]:
        """Map the request's field specs to their ``MetadataField`` ORM rows."""
        return [
            MetadataField(
                field_name=f.field_name,
                field_type=f.field_type,
                required=f.required,
                filterable=f.filterable,
                lexical=f.lexical,
                semantic=f.semantic,
                enum_values=f.enum_values,
                origin=f.origin,
                scope=f.scope,
                description=CollectionHelpers.clean_description(f.description),
            )
            for f in fields
        ]

    @staticmethod
    def clean_description(description: str | None) -> str | None:
        """Normalise a field description for storage: NUL-stripped and trimmed; blank → None.

        Postgres TEXT cannot hold U+0000, so every caller-supplied text bound for a column goes through
        ``TextSanitizer.strip_nul``; an all-whitespace description carries no meaning and is stored as
        "no description" rather than an invisible value.
        """
        if description is None:
            return None
        cleaned = TextSanitizer.strip_nul(description).strip()
        return cleaned or None


__all__ = ["CollectionHelpers"]
