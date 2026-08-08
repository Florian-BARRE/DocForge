# ====== Code Summary ======
# CollectionHelpers — the pure (store-free) logic behind the collections routes, kept out of
# router.py so the routes stay orchestration. It owns: the row → UI-contract mapping (the single
# secret-masking boundary), the metadata-field guards (mirror of the DB CHECK constraints), the
# pipeline-blob canonicalization (heal → validate → stamp), the search-blob shape guard, the
# metadata-field row building, and the embed vector-space fingerprint used to decide reindex.

# ====== Standard Library Imports ======

# ====== Third-Party Library Imports ======
from fastapi import HTTPException
from loggerplusplus import loggerplusplus

# ====== Internal Project Imports ======
from shared_libs.pipelines.ingest import (
    BlobNormalizationError,
    BlobNormalizer,
    IngestPipeline,
)
from shared_libs.public_models import FieldOrigin, FieldScope, FieldType
from shared_libs.services.db.postgresql.tables import Collection, MetadataField
from shared_libs.services.db.qdrant import RESERVED_PAYLOAD_KEYS

# ====== Local Project Imports ======
from ...utils.pipeline_validation import PipelineBlobValidator
from ...utils.search_blob_validation import SearchBlobValidator
from .models import CollectionModel, FieldSpecModel
from .redaction import redact_blob_secrets

# Payload keys the chunk point owns for its own machinery (id, ordinal, enable-filter). A
# filterable field is denormalised onto the point by NAME, so a field sharing one of these would
# overwrite it and corrupt search/deletion — reserved regardless of the current filterable flag,
# which can be toggled on later.
# "content" is the search-target sentinel for the chunk body; a metadata field of that name would
# be un-targetable (it always resolves to the body vectors), so it is reserved alongside the
# point's own payload keys (RESERVED_PAYLOAD_KEYS — the single source, shared with the writers).
_RESERVED_FIELD_NAMES = RESERVED_PAYLOAD_KEYS | {"content"}

# The embed-node config keys that define the vector space (a change to any means already-stored
# vectors were produced by a different/incompatible embedder → the collection must be reindexed).
_EMBED_VECTOR_KEYS = ("base_url", "model", "embed_sparse", "embed_semantic_fields")


class CollectionHelpers:
    """Static, store-free helpers for the collections routes (mapping, guards, blob logic)."""

    logger = loggerplusplus.bind(identifier="CollectionHelpers")

    def __new__(cls, *args: object, **kwargs: object) -> None:
        raise TypeError("CollectionHelpers is a static-only class and cannot be instantiated.")

    # -------------------- protected --------------------
    @staticmethod
    def _embed_vector_space(blob: dict) -> list:
        """A stable fingerprint of every embed node's vector-space-affecting config in a pipeline blob.

        Two blobs with the same fingerprint produce vectors in the same space; a difference means a
        reindex is required (e.g. a swapped embed model/provider, toggled sparse).
        """
        fingerprint: list = []

        def walk(nodes: list) -> None:
            for node in nodes:
                if node.get("family") == "embed":
                    config = node.get("config") or {}
                    fingerprint.append(
                        (
                            node.get("id"),
                            node.get("kind"),
                            tuple((key, config.get(key)) for key in _EMBED_VECTOR_KEYS),
                        )
                    )
                body = node.get("body")
                if isinstance(body, dict):
                    walk(body.get("nodes") or [])

        walk(blob.get("nodes") or [])
        return sorted(fingerprint)

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

    # -------------------- presets & blobs --------------------
    @staticmethod
    def preset_blob(preset: str | None) -> dict:
        """The stock ingestion blob a creation preset selects (used when no explicit pipeline is posted).

        Args:
            preset (str | None): ``"light"`` for the enrichment-free core, anything else the full default.

        Returns:
            dict: The selected stock blob as a JSON-ready dict.
        """
        blob = IngestPipeline.light_blob() if preset == "light" else IngestPipeline.default_blob()
        return blob.model_dump(mode="json")

    @staticmethod
    def canonical_pipeline(blob: dict) -> dict:
        """Heal a pipeline blob to the current engine, validate it, and return its stored form.

        The stored form is normalized (auto-migrated to the current-engine topology) and version-stamped,
        so a freshly written blob is already canonical and every subsequent run/upload fast-paths. A blob
        that cannot be migrated is a 422 with the explicit recovery, mirroring the structural validator.

        Args:
            blob (dict): The caller's (or default) pipeline blob.

        Returns:
            dict: The normalized, version-stamped blob to persist.

        Raises:
            HTTPException: 422 when the blob cannot be migrated or fails structural validation.
        """
        # 1. Auto-heal to the current-engine topology (a stale/unrecognisable blob is a clear 422).
        try:
            canonical = BlobNormalizer.normalize(blob)
        except BlobNormalizationError as exc:
            raise HTTPException(status_code=422, detail=f"Pipeline blob cannot be migrated: {exc}")

        # 2. Structural validation runs on the healed, stamp-free shape (the builder forbids extras).
        PipelineBlobValidator.validate(canonical)

        # 3. Persist the stamped canonical form so future reads fast-path.
        return BlobNormalizer.stamp(canonical)

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

    # -------------------- embed vector space --------------------
    @classmethod
    def embed_space_changed(cls, old_blob: dict, new_blob: dict) -> bool:
        """True when two pipeline blobs embed into DIFFERENT vector spaces (a reindex is required).

        Compares a stable fingerprint of every embed node's vector-space-affecting config; a
        difference means already-stored vectors were produced by an incompatible embedder (swapped
        model/provider, toggled sparse), so new documents must not be embedded into a space
        incompatible with the stored ones.
        """
        return cls._embed_vector_space(old_blob) != cls._embed_vector_space(new_blob)


__all__ = ["CollectionHelpers"]
