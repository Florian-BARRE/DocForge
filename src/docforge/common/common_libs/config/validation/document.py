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

from common_libs.config.pipeline import PipelineConfig
from common_libs.config.pipeline._helpers import PipelineConfigHelpers

# ====== Internal Project Imports ======
from common_libs.domain.metadata import SYSTEM_METADATA_FIELDS

# ====== Local Project Imports ======
from .document_helpers import ConfigFieldNormalizer

# Sentinel written by PipelineConfig.redacted_dict() in place of any secret value.
# A patch carrying this (or an empty secret) must NOT overwrite a real stored secret —
# it is the redacted value the UI echoed back, not a user-supplied credential.
_REDACTION_SENTINEL = "•••"


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
            "metadata_fields": [
                ConfigFieldNormalizer.to_dict(f) for f in collection.metadata_fields
            ],
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

        Secret preservation: a per-collection credential (api_key, token, …) is entered once
        in the UI and stored on the collection.  Config responses redact it to ``•••``, so any
        later config save echoes that sentinel (or an empty value) back.  Such a value must
        NOT overwrite the real stored secret — otherwise editing any stage would silently wipe
        the embed/rerank/LLM api_key and break both ingestion and query-time search.  When a
        patch carries a redacted/empty value for a secret-named key and the base holds a real
        one, the base value is kept.

        Args:
            base (dict): The current full config document.
            patch (dict): A partial document with only the keys to change.

        Returns:
            dict: A new merged document (inputs are not mutated).
        """
        out = copy.deepcopy(base)
        for key, value in patch.items():
            current = out.get(key)
            if isinstance(value, dict) and isinstance(current, dict):
                out[key] = cls.merge_patch(out[key], value)
            elif cls._is_mergeable_dict_list(value, current):
                # Provider chains (list of dicts) merge element-wise so per-element
                # secrets survive the redacted round-trip; differing lengths (a provider
                # added/removed) fall through to a wholesale replace below.
                out[key] = [
                    cls.merge_patch(b, p) for b, p in zip(current, value)
                ]
            elif cls._is_redacted_secret(key, value) and current:
                # Keep the real stored secret; the patch only echoed the redacted placeholder.
                continue
            else:
                out[key] = copy.deepcopy(value)
        return out

    @staticmethod
    def _is_mergeable_dict_list(value: Any, current: Any) -> bool:
        """
        Return True when both ``value`` and ``current`` are equal-length lists of dicts.

        Such lists (e.g. a provider chain) are merged element-wise so per-element secret
        preservation applies; any other list is replaced wholesale by the caller.

        Args:
            value (Any): The incoming patch value.
            current (Any): The existing base value at the same key.

        Returns:
            bool: True if element-wise dict merge is appropriate.
        """
        return (
            isinstance(value, list) and isinstance(current, list)
            and len(value) == len(current) and len(value) > 0
            and all(isinstance(v, dict) for v in value)
            and all(isinstance(c, dict) for c in current)
        )

    @staticmethod
    def _is_redacted_secret(key: str, value: Any) -> bool:
        """
        Decide whether a (key, value) pair is a redacted/empty secret that must not overwrite.

        Args:
            key (str): The patch key being merged.
            value (Any): The incoming value for that key.

        Returns:
            bool: True when ``key`` names a credential and ``value`` is the redaction sentinel,
                an empty string, or None (i.e. carries no real new secret).
        """
        if not (isinstance(key, str) and PipelineConfigHelpers.is_secret_key(key)):
            return False
        return value in (_REDACTION_SENTINEL, "", None)

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
            f["field_name"]: ConfigFieldNormalizer.to_dict(f) for f in SYSTEM_METADATA_FIELDS
        }
        for raw in custom or []:
            spec = ConfigFieldNormalizer.to_dict(raw)
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
