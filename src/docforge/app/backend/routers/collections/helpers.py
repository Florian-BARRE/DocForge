# ====== Code Summary ======
# CollectionHelpers — the pure (store-free) logic behind the collections routes, kept out of
# router.py so the routes stay orchestration. It owns: the row → UI-contract mapping (the single
# secret-masking boundary), the metadata-field guards (mirror of the DB CHECK constraints), the
# search-blob shape guard, and the metadata-field row building. Pipeline-blob concerns (preset,
# canonicalize, embed vector-space) live in blob_helpers.py.

# ====== Standard Library Imports ======

# ====== Third-Party Library Imports ======
from fastapi import HTTPException
from loggerplusplus import loggerplusplus

# ====== Internal Project Imports ======
from shared_libs.pipelines.blob_secrets import redact_blob_secrets
from shared_libs.pipelines.ingest import BlobNormalizer
from shared_libs.public_models import FieldOrigin, FieldScope, FieldType
from shared_libs.services.db.postgresql.tables import Collection, MetadataField
from shared_libs.services.db.qdrant import RESERVED_PAYLOAD_KEYS

# ====== Local Project Imports ======
from ...utils.search_blob_validation import SearchBlobValidator
from .models import CollectionModel, FieldSpecModel

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
    def to_model(cls, collection: Collection, fields: list[MetadataField]) -> CollectionModel:
        """Map the rows to the UI contract (shared by every read path).

        Provider secrets (api_key on every provider node of the pipeline AND search blobs) are masked
        here — the ONE serialisation boundary every read path funnels through — so a live key is never
        echoed to a client. The stored blobs keep the real keys; only this outbound copy is masked.
        """
        return CollectionModel(
            id=str(collection.id),
            name=collection.name,
            supported_formats=list(collection.supported_formats),
            max_file_size_bytes=collection.max_file_size_bytes,
            job_timeout_seconds=collection.job_timeout_seconds,
            needs_reindex=collection.needs_reindex,
            created_at=collection.created_at,
            pipeline=redact_blob_secrets(cls.public_pipeline(collection.pipeline)),
            search=redact_blob_secrets(collection.search),
            fields=[
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
                )
                for row in fields
            ],
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
            # Chunk-scope lexical has no producer: the embed node writes chunk-scope SEMANTIC (dense)
            # vectors and the meta-vector facade is document-scope only, so a chunk-scope lexical field
            # would declare a meta_<slug>_bm25 vector nothing ever fills — a silent-empty search. Reject
            # it up front rather than accept a config that can never return results.
            if spec.scope == FieldScope.CHUNK and spec.lexical:
                raise HTTPException(
                    status_code=422,
                    detail=f"Field '{spec.field_name}': chunk-scope lexical search is not supported "
                    f"(no BM25 producer for chunk metadata) — use semantic, or document scope.",
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
            )
            for f in fields
        ]


__all__ = ["CollectionHelpers"]
