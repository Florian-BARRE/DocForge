# ====== Code Summary ======
# Static, stateless helpers for ConfigRepository: pipeline-version increment and
# metadata-field ORM construction. Extracted to keep ConfigRepository focused on
# session-bound data-access operations.

# ====== Standard Library Imports ======
import re
from typing import Any

# ====== Third-Party Library Imports ======
from loggerplusplus import loggerplusplus

# ====== Local Project Imports ======
from ..models import MetadataFieldModel


class ConfigRepoHelpers:
    """
    Pure, stateless helpers for ConfigRepository.

    Contains utilities that depend neither on a database session nor on instance
    state: pipeline-version tag incrementing and building a MetadataFieldModel
    from a normalized field spec.
    """

    logger = loggerplusplus.bind(identifier="ConfigRepoHelpers")

    def __new__(cls, *args: object, **kwargs: object) -> None:
        """Block instantiation — this is a static-only helper class."""
        raise TypeError("ConfigRepoHelpers is a static-only class and cannot be instantiated.")

    @staticmethod
    def next_pipeline_version(current: str) -> str:
        """
        Increment the trailing integer of a pipeline_version tag (``v1`` → ``v2``).

        Falls back to appending ``-2`` when no trailing integer is present.

        Args:
            current (str): The current pipeline_version tag.

        Returns:
            str: The incremented pipeline_version tag.
        """
        match = re.search(r"(\d+)$", current or "")
        if match:
            return f"{current[: match.start()]}{int(match.group(1)) + 1}"
        return f"{current or 'v1'}-2"

    @staticmethod
    def _attr(obj: Any, name: str, default: Any = None) -> Any:
        """
        Read an attribute from either an ORM object or a plain dict.

        Args:
            obj (Any): ORM model instance or dict.
            name (str): Attribute / key name.
            default (Any): Fallback when absent.

        Returns:
            Any: The value, or ``default``.
        """
        if isinstance(obj, dict):
            return obj.get(name, default)
        return getattr(obj, name, default)

    # Gate keys that change run-behavior only (not the produced output) → never reindex-relevant.
    _NON_REINDEX_GATE_KEYS: frozenset[str] = frozenset({"failure_policy", "on_degraded"})

    @staticmethod
    def _strip_non_reindex_keys(value: Any) -> Any:
        """
        Return a deep copy of ``value`` with all non-reindex gate keys removed.

        Recursively drops ``failure_policy`` and ``on_degraded`` from every nested dict so
        toggling a chain's exhaustion policy never registers as an indexing-config change.
        These keys live only on gate objects; stripping them everywhere is safe and avoids
        having to know each stage's exact gate location. Lists are walked element-wise; all
        other scalars pass through unchanged.

        Args:
            value (Any): A pipeline stage config fragment (dict / list / scalar).

        Returns:
            Any: The same structure with the non-reindex gate keys removed.
        """
        # 1. Dict — copy, drop the policy keys, recurse into the remaining values.
        if isinstance(value, dict):
            return {
                k: ConfigRepoHelpers._strip_non_reindex_keys(v)
                for k, v in value.items()
                if k not in ConfigRepoHelpers._NON_REINDEX_GATE_KEYS
            }
        # 2. List — recurse element-wise (e.g. a provider chain list).
        if isinstance(value, list):
            return [ConfigRepoHelpers._strip_non_reindex_keys(item) for item in value]
        # 3. Scalar — unchanged.
        return value

    @staticmethod
    def reindex_diff(
        *,
        old_embedding_model: str,
        new_embedding_model: str,
        old_pipeline: dict[str, Any] | None,
        new_pipeline: dict[str, Any],
        old_fields: list[Any],
        new_fields: list[Any],
    ) -> tuple[bool, list[str]]:
        """
        Classify a config change as reindex-relevant (or not) and explain exactly why.

        Only changes that invalidate already-indexed documents count:
          - the embedding model (vectors become incompatible);
          - the *indexing* pipeline — every ``pipeline`` section EXCEPT ``search`` (which is
            query-time only, so search-config edits never require a reindex);
          - the *searchable* metadata schema — a field gaining/losing a ``semantic`` or
            ``lexical`` vector (a plain or filter-only field add/remove does NOT).

        Non-critical changes (search config, optional non-searchable metadata add/remove,
        labels, required flags) return ``(False, [])`` so existing documents stay fresh.

        Args:
            old_embedding_model (str): Embedding model before the change.
            new_embedding_model (str): Embedding model after the change.
            old_pipeline (dict | None): Pipeline config before the change.
            new_pipeline (dict): Pipeline config after the change.
            old_fields (list): Current metadata fields (ORM objects).
            new_fields (list): Merged metadata fields after the change (dicts).

        Returns:
            tuple[bool, list[str]]: ``(reindex_relevant, human_readable_reasons)``.
        """
        reasons: list[str] = []

        # 1. Embedding model — full reindex (vector space changes)
        if new_embedding_model != old_embedding_model:
            reasons.append(
                f"Modèle d'embedding modifié ({old_embedding_model} → {new_embedding_model})"
            )

        # 2. Indexing pipeline — every stage except query-time 'search'.
        # The chain failure policy (failure_policy / on_degraded) is run-behavior only: it
        # changes WHAT happens on exhaustion (raise vs degrade), never WHICH provider runs nor
        # the bytes it produces — so it is NOT reindex-relevant. Strip those two keys from every
        # gate before comparing. Gate THRESHOLDS (min_score / max_duration_ms) stay in the
        # comparison: they can change which provider is accepted → different output → reindex.
        old_idx = {
            k: ConfigRepoHelpers._strip_non_reindex_keys(v)
            for k, v in (old_pipeline or {}).items() if k != "search"
        }
        new_idx = {
            k: ConfigRepoHelpers._strip_non_reindex_keys(v)
            for k, v in (new_pipeline or {}).items() if k != "search"
        }
        for stage in sorted(set(old_idx) | set(new_idx)):
            if old_idx.get(stage) != new_idx.get(stage):
                reasons.append(f"Configuration d'indexation « {stage} » modifiée")

        # 3. Searchable metadata schema — only fields carrying a semantic/lexical vector
        def _searchable(fields: list[Any]) -> set[tuple[str, bool, bool]]:
            out: set[tuple[str, bool, bool]] = set()
            for f in fields:
                sem = bool(ConfigRepoHelpers._attr(f, "semantic"))
                lex = bool(ConfigRepoHelpers._attr(f, "lexical"))
                if sem or lex:
                    out.add((str(ConfigRepoHelpers._attr(f, "field_name")), sem, lex))
            return out

        old_s = _searchable(old_fields)
        new_s = _searchable(new_fields)
        for name, _sem, _lex in sorted(new_s - old_s):
            reasons.append(f"Champ recherchable « {name} » ajouté ou modifié")
        for name in sorted({n for n, _, _ in old_s} - {n for n, _, _ in new_s}):
            reasons.append(f"Champ recherchable « {name} » retiré")

        return (len(reasons) > 0, reasons)

    @staticmethod
    def build_field(spec: dict[str, Any]) -> MetadataFieldModel:
        """
        Build a MetadataFieldModel from a normalized metadata-field dict (no collection_id).

        Args:
            spec (dict[str, Any]): Normalized metadata-field specification.

        Returns:
            MetadataFieldModel: The unattached ORM instance.
        """
        return MetadataFieldModel(
            field_name=spec["field_name"],
            field_type=spec.get("field_type", "string"),
            required=bool(spec.get("required", False)),
            filterable=bool(spec.get("filterable", False)),
            lexical=bool(spec.get("lexical", False)),
            semantic=bool(spec.get("semantic", False)),
            enum_values=spec.get("enum_values"),
            is_system=bool(spec.get("is_system", False)),
        )
