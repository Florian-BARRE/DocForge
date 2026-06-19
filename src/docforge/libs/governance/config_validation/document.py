# ====== Code Summary ======
# ConfigDocument — the canonical, editable representation of a collection's configuration.
# A single shape is shared by every config path (create / state / export / update / import /
# reset / rollback) so they can never drift.  It is the editable subset of a collection:
# identity (id/name/pipeline_version/needs_reindex) is *state*, not part of the editable doc.

# ====== Standard Library Imports ======
from __future__ import annotations

import copy
from typing import Any

# ====== Third-Party Library Imports ======
from loggerplusplus import loggerplusplus

# ====== Internal Project Imports ======
from libs.core.metadata import SYSTEM_METADATA_FIELDS, MetaFieldSpec
from libs.core.contracts.pipeline_config import PipelineConfig

class ConfigDocument:
    """
    Static helpers building / merging the canonical editable config document.

    The document shape::

        {
          "supported_formats": list[str],
          "max_file_size_bytes": int,
          "locality_policy": str,
          "embedding_model": str,
          "unknown_field_policy": str,
          "pipeline": dict,              # serialized PipelineConfig
          "metadata_fields": list[dict], # normalized MetaFieldSpec dicts (system + custom)
        }
    """

    logger = loggerplusplus.bind(identifier="ConfigDocument")

    def __new__(cls, *args: object, **kwargs: object) -> None:
        raise TypeError("ConfigDocument is a static-only class and cannot be instantiated.")

    # ─── Construction ───────────────────────────────────────────────────────────

    @classmethod
    def from_collection(cls, collection: Any) -> dict[str, Any]:
        """
        Build the editable config document from a persisted CollectionModel.

        Args:
            collection (Any): A CollectionModel with its metadata_fields eagerly loaded.

        Returns:
            dict: The canonical editable config document.
        """
        # 1. Contract + pipeline scalars
        # 2. Normalize every persisted metadata field into the canonical key set
        return {
            "supported_formats": list(collection.supported_formats),
            "max_file_size_bytes": collection.max_file_size_bytes,
            "locality_policy": collection.locality_policy,
            "embedding_model": collection.embedding_model,
            "unknown_field_policy": collection.unknown_field_policy,
            "pipeline": dict(collection.pipeline or {}),
            "metadata_fields": [cls._field_to_dict(f) for f in collection.metadata_fields],
        }

    @classmethod
    def defaults(cls, collection: Any) -> dict[str, Any]:
        """
        Build a reset document: default pipeline + system-only metadata, identity preserved.

        Reset restores the *pipeline* and *metadata schema* to their defaults while keeping the
        collection's contract identity (accepted formats, size cap, locality, embedding model,
        unknown-field policy) — those define the vector space / admission contract and must not
        be silently wiped.

        Args:
            collection (Any): The collection whose contract identity is preserved.

        Returns:
            dict: A default config document.
        """
        return {
            "supported_formats": list(collection.supported_formats),
            "max_file_size_bytes": collection.max_file_size_bytes,
            "locality_policy": collection.locality_policy,
            "embedding_model": collection.embedding_model,
            "unknown_field_policy": collection.unknown_field_policy,
            "pipeline": PipelineConfig().to_dict(),
            "metadata_fields": cls.merge_metadata_schema([]),
        }

    @classmethod
    def resolve_pipeline(cls, doc: dict[str, Any]) -> dict[str, Any]:
        """
        Return a copy of the document with its pipeline fully resolved (defaults filled).

        Persisting the resolved pipeline (rather than the caller's partial dict) makes the stored
        config self-describing: every knob is explicit, nothing is hidden behind read-time defaults.

        Args:
            doc (dict): A config document whose ``pipeline`` may be empty/partial.

        Returns:
            dict: A new document with ``pipeline`` = the full serialized PipelineConfig.
        """
        out = dict(doc)
        out["pipeline"] = PipelineConfig.from_dict(doc.get("pipeline")).to_dict()
        return out

    # ─── Merging ────────────────────────────────────────────────────────────────

    @classmethod
    def merge_patch(cls, base: dict[str, Any], patch: dict[str, Any]) -> dict[str, Any]:
        """
        Deep-merge a partial patch onto a base document (provided keys replace existing).

        Nested dicts (e.g. ``pipeline.chunk``) merge recursively so a patch can touch a single
        knob; lists and scalars (incl. ``metadata_fields``) replace wholesale.

        Args:
            base (dict): The current full config document.
            patch (dict): A partial document with only the keys to change.

        Returns:
            dict: A new merged document (inputs are not mutated).
        """
        out = copy.deepcopy(base)
        for key, value in patch.items():
            if isinstance(value, dict) and isinstance(out.get(key), dict):
                out[key] = cls.merge_patch(out[key], value)
            else:
                out[key] = copy.deepcopy(value)
        return out

    @classmethod
    def merge_metadata_schema(cls, custom: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """
        Merge the always-present system metadata fields with user-provided fields.

        System fields are injected from the catalog.  A submitted field whose name matches a
        system field overrides only its search flags (it stays flagged ``is_system``); any other
        submitted field is appended as a custom business field (``is_system=False``).

        Args:
            custom (list[dict]): User-provided metadata field dicts (may be empty).

        Returns:
            list[dict]: The merged, normalized metadata schema (system fields first).
        """
        by_name: dict[str, dict[str, Any]] = {
            f["field_name"]: cls._field_to_dict(f) for f in SYSTEM_METADATA_FIELDS
        }
        for raw in custom or []:
            spec = cls._field_to_dict(raw)
            name = spec["field_name"]
            if name in by_name:
                # Override a system field's search behavior only; keep it flagged as system.
                by_name[name].update({
                    "filterable": spec["filterable"], "lexical": spec["lexical"],
                    "semantic": spec["semantic"],
                })
            else:
                spec["is_system"] = False
                by_name[name] = spec
        return list(by_name.values())

    # ─── Private helpers ──────────────────────────────────────────────────────────

    @classmethod
    def _field_to_dict(cls, field: Any) -> dict[str, Any]:
        """
        Normalize a metadata field (ORM row, Pydantic model, or dict) to the canonical keys.

        Args:
            field (Any): A MetadataFieldModel, MetaFieldSpec, or plain dict.

        Returns:
            dict: A dict with exactly the persisted metadata-field keys, defaults filled.
        """
        # 1. Coerce any supported source into a plain dict
        if hasattr(field, "model_dump"):
            src = field.model_dump()
        elif isinstance(field, dict):
            src = field
        else:
            src = {k: getattr(field, k, None) for k in MetaFieldSpec.model_fields}

        # 2. Project onto the canonical key set with sensible defaults
        return {
            "field_name": src["field_name"],
            "field_type": src.get("field_type", "string"),
            "required": bool(src.get("required", False)),
            "filterable": bool(src.get("filterable", False)),
            "lexical": bool(src.get("lexical", False)),
            "semantic": bool(src.get("semantic", False)),
            "enum_values": src.get("enum_values"),
            "is_system": bool(src.get("is_system", False)),
        }
