# ====== Code Summary ======
# MetagenChecks — validates the S5b metagen block of a collection config: every
# pipeline.metagen.targets[*] must bind an existing metadata_field authored with origin="generated"
# (never a system/user field), with no duplicate target, a usable scope, and a (recommended) prompt;
# a metagen with work to do but no LLM provider is an error; a generated field nobody binds is a
# warning. Pure static validation logic; no logging. Issue shape matches MetadataChecks
# ({code, severity, field, message}) so the aggregated list stays uniform.

# ====== Standard Library Imports ======
from __future__ import annotations

from typing import Any, get_args

# ====== Internal Project Imports ======
from common_libs.config.pipeline.stages.metagen_config import MetaGenTarget

# Allowed generation scopes — derived from MetaGenTarget.scope so this checker can never drift from
# what the config model actually accepts (mirrors metadata_checks' _ALLOWED_FIELD_TYPES idiom).
_ALLOWED_SCOPES: frozenset[str] = frozenset(get_args(MetaGenTarget.model_fields["scope"].annotation))


class MetagenChecks:
    """
    Static checker for the S5b metagen config block (``pipeline.metagen``).

    Validates each generation target against the collection's metadata schema:
    - ``target.field`` references an existing metadata field with ``origin="generated"``.
    - No two targets bind the same field (duplicate detection).
    - ``scope`` is one of the values allowed by ``MetaGenTarget`` (chunk / document).
    - A target with a blank prompt is flagged (a generic instruction would be used instead).
    - Metagen has targets but no LLM provider configured → error (it could never run).
    - A generated field that no target binds → warning (it would never be populated).
    """

    def __new__(cls, *args: object, **kwargs: object) -> None:
        raise TypeError("MetagenChecks is a static-only class and cannot be instantiated.")

    @staticmethod
    def check_metagen(doc: dict[str, Any], issues: list[dict[str, Any]]) -> None:
        """
        Validate the metagen targets ↔ generated-metadata-field coherence.

        Args:
            doc (dict): A canonical config document (carries ``pipeline`` + ``metadata_fields``).
            issues (list[dict]): Accumulator — issues are appended in place.
        """
        # 1. Pull the metagen block and the schema's generated/known field names from the doc.
        metagen = (doc.get("pipeline") or {}).get("metagen") or {}
        targets = metagen.get("targets") or []
        chain = metagen.get("chain") or []
        fields = doc.get("metadata_fields") or []
        all_names = {f.get("field_name") for f in fields if f.get("field_name")}
        generated_names = {
            f.get("field_name") for f in fields if f.get("field_name") and f.get("origin") == "generated"
        }

        # 2. Per-target checks (field reference + duplicate + prompt + scope).
        bound: set[str] = set()
        seen: set[str] = set()
        for idx, target in enumerate(targets):
            MetagenChecks._check_target(idx, target, all_names, generated_names, seen, bound, issues)

        # 3. Metagen has work (at least one target) but no LLM provider → it could never run.
        if targets and not chain:
            issues.append(_issue(
                "metagen.no_provider", "error", "pipeline.metagen.chain",
                "Metagen has targets but no LLM provider is configured — add a provider to the chain.",
            ))

        # 4. A generated field that no target binds will never be populated → advisory warning.
        for name in sorted(generated_names - bound):
            issues.append(_issue(
                "metagen.orphan_field", "warning", f"metadata_fields.{name}",
                f"Generated field {name!r} has no metagen target; it will never be populated.",
            ))

    @staticmethod
    def _check_target(
        idx: int,
        target: dict[str, Any],
        all_names: set[Any],
        generated_names: set[Any],
        seen: set[str],
        bound: set[str],
        issues: list[dict[str, Any]],
    ) -> None:
        """
        Validate one ``pipeline.metagen.targets[idx]`` entry, appending any issues in place.

        Args:
            idx (int): The target's index (used to build a precise issue field path).
            target (dict): The target entry ({field, prompt, scope}).
            all_names (set): Every metadata field name in the schema.
            generated_names (set): Metadata field names authored with origin="generated".
            seen (set[str]): Field names already used by an earlier target (duplicate detection).
            bound (set[str]): Accumulator of every field a target binds (orphan detection).
            issues (list[dict]): Accumulator — issues are appended in place.
        """
        fpath = f"pipeline.metagen.targets[{idx}]"
        field_name = (target.get("field") or "").strip()
        bound.add(field_name)

        # 1. Field reference must be present and resolve to a generated metadata field.
        if not field_name:
            issues.append(_issue(
                "metagen.target_missing_field", "error", fpath,
                "A metagen target is missing its 'field' reference.",
            ))
        elif field_name not in generated_names:
            if field_name in all_names:
                issues.append(_issue(
                    "metagen.target_not_generated", "error", f"{fpath}.field",
                    f"Target field {field_name!r} must be a metadata field with origin='generated'.",
                ))
            else:
                issues.append(_issue(
                    "metagen.target_unknown_field", "error", f"{fpath}.field",
                    f"Target field {field_name!r} does not exist in the metadata schema.",
                ))

        # 2. No two targets may bind the same field.
        if field_name and field_name in seen:
            issues.append(_issue(
                "metagen.duplicate_target", "error", f"{fpath}.field",
                f"Duplicate metagen target for field {field_name!r}.",
            ))
        seen.add(field_name)

        # 3. A blank prompt still runs (with a generic instruction) → advisory warning.
        if not (target.get("prompt") or "").strip():
            issues.append(_issue(
                "metagen.empty_prompt", "warning", f"{fpath}.prompt",
                f"Metagen target {field_name or '?'!r} has no prompt; a generic instruction will be used.",
            ))

        # 4. Scope must be one of the model-allowed values (defense in depth — parse also enforces it).
        scope = target.get("scope", "chunk")
        if scope not in _ALLOWED_SCOPES:
            issues.append(_issue(
                "metagen.bad_scope", "error", f"{fpath}.scope",
                f"Metagen target scope {scope!r} must be one of {sorted(_ALLOWED_SCOPES)}.",
            ))


# ─── Module-level helper (not exposed in __all__) ────────────────────────────

def _issue(code: str, severity: str, field: str, message: str) -> dict[str, Any]:
    """Build a single validation issue record."""
    return {"code": code, "severity": severity, "field": field, "message": message}
