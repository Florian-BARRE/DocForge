# ====== Code Summary ======
# ConfigDiffer — the structured diff of two config-version snapshots ({pipeline, search}). Paths are
# JSON-pointer style ("/pipeline/nodes/parse/config/max_pages"): a list whose items all carry a unique
# string ``id`` (graph nodes) is keyed by that id, so a node edit reads as a change inside that node
# rather than an index shuffle (the order of id-keyed items is not diffed — the graph is wired by
# transitions, not by list order); any other list is compared as a whole value. The diff is computed on
# the REAL snapshots but every reported value is read from their MASKED twins (same shape — masking
# only swaps secret strings), so a rotated key shows as a change with both sides masked and no secret
# ever leaves the server. ``summary`` is the coarse "which top-level pipeline nodes / search changed"
# label list shown in the history listing.

# ====== Standard Library Imports ======
from dataclasses import dataclass
from typing import Any, Literal

# ====== Internal Project Imports ======
from shared_libs.pipelines.blob_secrets import redact_config_snapshot

ChangeOp = Literal["added", "removed", "changed"]

# The summary label for a pipeline change outside the top-level nodes (transitions, bindings, …).
_WIRING_LABEL = "pipeline:(graph)"


@dataclass(frozen=True, slots=True)
class ConfigChange:
    """One changed path between two snapshots (values already masked)."""

    path: str
    op: ChangeOp
    before: Any = None
    after: Any = None


class ConfigDiffer:
    """Static structured diff + change summary of config-version snapshots."""

    def __new__(cls, *args: object, **kwargs: object) -> None:
        raise TypeError("ConfigDiffer is a static-only class and cannot be instantiated.")

    @classmethod
    def diff(cls, before: dict | None, after: dict | None) -> list[ConfigChange]:
        """
        Diff two snapshots path by path, reporting masked values only.

        Args:
            before (dict | None): The older snapshot (real secrets).
            after (dict | None): The newer snapshot (real secrets).

        Returns:
            list[ConfigChange]: Every added / removed / changed path, in walk order.
        """
        # 1. Mask both sides once; the walk compares the real trees but reports the masked ones.
        changes: list[ConfigChange] = []
        masked_before = redact_config_snapshot(before or {})
        masked_after = redact_config_snapshot(after or {})
        cls._walk(before or {}, after or {}, masked_before, masked_after, "", changes)
        return changes

    @classmethod
    def summary(cls, before: dict | None, after: dict | None) -> list[str]:
        """
        Name the coarse areas that changed: ``pipeline:<node id>``, ``pipeline:(graph)``, ``search``.

        Args:
            before (dict | None): The predecessor snapshot (None = no predecessor → no summary).
            after (dict | None): The snapshot being summarised.

        Returns:
            list[str]: Sorted, de-duplicated change labels (empty when nothing differs).
        """
        # 1. A first version has nothing to be compared against.
        if before is None:
            return []
        # 2. Collapse each changed path to its top-level area (a node id, the graph wiring, search).
        labels: set[str] = set()
        for change in cls.diff(before, after):
            parts = change.path.strip("/").split("/")
            if parts[0] == "pipeline" and len(parts) > 2 and parts[1] == "nodes":
                labels.add(f"pipeline:{parts[2]}")
            elif parts[0] == "pipeline":
                labels.add(_WIRING_LABEL)
            else:
                labels.add(parts[0])
        return sorted(labels)

    @classmethod
    def _walk(
        cls, raw_b: Any, raw_a: Any, mask_b: Any, mask_a: Any, path: str, out: list[ConfigChange]
    ) -> None:
        """Recurse dicts and id-keyed lists; report a leaf/whole-value difference with masked values."""
        # 1. Dicts: per-key, an absent side is an add/remove of the whole (masked) value.
        if isinstance(raw_b, dict) and isinstance(raw_a, dict):
            cls._walk_keyed(raw_b, raw_a, mask_b, mask_a, path, out)
            return
        # 2. Id-keyed lists (graph nodes): re-key by id, then walk like a dict.
        keyed_b, keyed_a = cls._by_id(raw_b), cls._by_id(raw_a)
        if keyed_b is not None and keyed_a is not None:
            cls._walk_keyed(keyed_b, keyed_a, cls._by_id(mask_b), cls._by_id(mask_a), path, out)
            return
        # 3. Anything else is compared as one value.
        if raw_b != raw_a:
            out.append(ConfigChange(path=path or "/", op="changed", before=mask_b, after=mask_a))

    @classmethod
    def _walk_keyed(
        cls, raw_b: dict, raw_a: dict, mask_b: Any, mask_a: Any, path: str, out: list[ConfigChange]
    ) -> None:
        """Walk two key → value maps (dict keys, or node ids) in a stable sorted order."""
        for key in sorted(set(raw_b) | set(raw_a), key=str):
            child = f"{path}/{cls._escape(str(key))}"
            if key not in raw_a:
                out.append(ConfigChange(path=child, op="removed", before=mask_b[key]))
            elif key not in raw_b:
                out.append(ConfigChange(path=child, op="added", after=mask_a[key]))
            else:
                cls._walk(raw_b[key], raw_a[key], mask_b[key], mask_a[key], child, out)

    @staticmethod
    def _by_id(value: Any) -> dict[str, Any] | None:
        """Key a list of dicts by their unique string ``id`` (None when the list is not id-keyed)."""
        if not isinstance(value, list) or not value:
            return None
        ids = [item.get("id") if isinstance(item, dict) else None for item in value]
        if not all(isinstance(i, str) for i in ids) or len(set(ids)) != len(ids):
            return None
        return dict(zip(ids, value, strict=True))

    @staticmethod
    def _escape(segment: str) -> str:
        """JSON-pointer escape of one path segment (``~`` → ``~0``, ``/`` → ``~1``)."""
        return segment.replace("~", "~0").replace("/", "~1")


__all__ = ["ConfigChange", "ConfigDiffer"]
