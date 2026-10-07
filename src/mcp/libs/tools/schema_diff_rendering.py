# ====== Code Summary ======
# Schema-op helpers for the update_collection tool: decide whether a field_ops list is DESTRUCTIVE
# (a remove deletes values; a rename re-keys search filters/vectors) and so needs confirm=true, and
# render a SchemaDiff compactly — only its non-empty buckets, one short line each.

from __future__ import annotations

# ====== Standard Library Imports ======
from typing import Any

# ====== Third-Party Library Imports ======
from docforge_sdk.models import SchemaDiff

# Ops that must be confirmed before they are applied (the rest are additive / in-place).
_CONFIRM_OPS = frozenset({"remove", "rename"})

CONFIRM_HINT = "re-run with confirm=true to apply"


class SchemaDiffRenderer:
    """Destructive-op detection + compact SchemaDiff rendering for the MCP surface."""

    @staticmethod
    def needs_confirm(field_ops: list[dict[str, Any]] | None) -> bool:
        """
        Whether a field_ops list contains a remove or a rename.

        Args:
            field_ops (list[dict[str, Any]] | None): The raw ops the LLM passed.

        Returns:
            bool: True when applying them must be confirmed first.
        """
        return any(op.get("op") in _CONFIRM_OPS for op in field_ops or [])

    @staticmethod
    def render(diff: SchemaDiff) -> dict[str, Any]:
        """
        Render a SchemaDiff as a compact dict carrying only its non-empty buckets.

        Args:
            diff (SchemaDiff): The diff from the PATCH response.

        Returns:
            dict[str, Any]: e.g. ``{"removed": ["x (12 values lost)"], "renamed": ["a -> b"]}``;
                ``{}`` when the schema was untouched.
        """
        # 1. Removals carry their value loss inline — the one number that matters before confirming.
        out: dict[str, Any] = {
            "added": diff.added,
            "modified": [f"{m.field_name}: {', '.join(m.changed_attrs)}" for m in diff.modified],
            "removed": [
                f"{name} ({diff.values_lost.get(name, 0)} values lost)" for name in diff.removed
            ],
            "renamed": [f"{r.from_name} -> {r.to_name}" for r in diff.renamed],
            "reindex_required_fields": diff.reindex_required_fields,
        }
        # 2. Drop empty buckets (token economy).
        return {key: value for key, value in out.items() if value}


__all__ = ["SchemaDiffRenderer", "CONFIRM_HINT"]
