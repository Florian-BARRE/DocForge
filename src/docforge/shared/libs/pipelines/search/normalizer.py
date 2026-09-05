# ====== Code Summary ======
# SearchBlobNormalizer — the READ-side auto-heal for a stored SEARCH graph blob, the search-side
# counterpart of the ingest BlobNormalizer. A search blob is stored fully-expanded (nodes /
# transitions / bindings), so — unlike the ingest heal, which round-trips through a stage-level
# PipelineState via a dedicated reader+assembler that search has no analog of — this heal works at
# the CONFIG level: it re-validates every action node's stored config against the node's CURRENT
# registered Config model, applying that model's own before-validators (normalisation) and dropping
# fields the current model no longer declares (registry drift — a renamed/removed knob). A config
# whose ONLY problem is such stale extra keys is HEALED (the keys are stripped so the extra="forbid"
# build no longer bricks); a config broken in any other way (wrong type, unknown family/kind) is left
# to raise a clear SearchBlobNormalizationError rather than being silently mangled. A blob with no
# "nodes" (the {} stock-default sentinel) is a NO-OP — it carries no stored config to heal.

# ====== Standard Library Imports ======
import copy
from collections.abc import Mapping
from typing import Any

# ====== Third-Party Library Imports ======
from loggerplusplus import loggerplusplus
from pydantic import ValidationError

# ====== Internal Project Imports ======
from shared_libs.pipelines.registry import NodeRegistry

# The pydantic v2 error type raised for a key rejected by ``extra="forbid"`` — the SIGNATURE of
# registry drift (a config field the current model no longer declares). Only these errors are
# healable by stripping; any other validation error is a genuinely broken config.
_EXTRA_FORBIDDEN = "extra_forbidden"


class SearchBlobNormalizationError(Exception):
    """A stored search blob cannot be reconciled with the current engine (broken config / kind)."""


class SearchBlobNormalizer:
    """
    Static heal for a stored search blob: reconcile every node's config to the current registry.

    Stateless. It never runs the engine and touches only stored config values — the topology
    (nodes / transitions / bindings) is preserved verbatim; the graph builder + validator still
    have the final say on structural correctness at run time.
    """

    logger = loggerplusplus.bind(identifier="SearchBlobNormalizer")

    def __new__(cls, *args: object, **kwargs: object) -> None:
        raise TypeError("SearchBlobNormalizer is a static-only class and cannot be instantiated.")

    @classmethod
    def normalize(cls, blob: Mapping[str, Any]) -> dict[str, Any]:
        """
        Heal a stored search blob to the current engine's config shape (topology untouched).

        Args:
            blob (Mapping): The stored ``collection.search`` value (fully-expanded graph, or the
                ``{}`` / no-``nodes`` stock-default sentinel).

        Returns:
            dict: A build-ready blob — byte-identical to the input when no drift was present,
            otherwise the same graph with each node's config reconciled to its current model.

        Raises:
            SearchBlobNormalizationError: A node names a family/kind the registry no longer knows,
                or a config is broken in a way stripping stale keys cannot repair.
        """
        # 1. No "nodes" → the stock-default sentinel ({}): nothing stored to heal, hand it back as-is.
        if not blob.get("nodes"):
            return dict(blob)

        # 2. Deep-copy so the heal never mutates the caller's stored dict, then walk the graph.
        healed = copy.deepcopy(dict(blob))
        cls.__heal_nodes(healed.get("nodes") or [])
        return healed

    @classmethod
    def __heal_nodes(cls, nodes: list[Any]) -> None:
        """
        Reconcile every action node's config in a node list, recursing groups + ForEach bodies.

        Args:
            nodes (list): The ``nodes`` list of a group blob (mutated in place).
        """
        # 1. Classify each node by its shape: an action (family+kind) carries a config to heal; a
        #    group nests more nodes; a ForEach nests a body group — both are walked recursively.
        for node in nodes:
            if not isinstance(node, Mapping):
                continue
            if "family" in node and "kind" in node:
                cls.__heal_action_config(node)
            if node.get("nodes"):
                cls.__heal_nodes(node["nodes"])
            body = node.get("body")
            if isinstance(body, Mapping) and body.get("nodes"):
                cls.__heal_nodes(body["nodes"])

    @classmethod
    def __heal_action_config(cls, node: dict[str, Any]) -> None:
        """
        Reconcile ONE action node's stored config to its current registered Config model.

        A config that validates clean is left untouched (byte-identical). One whose only fault is
        stale extra keys (registry drift) has those keys stripped so the ``extra="forbid"`` build no
        longer bricks. Any other fault — or a kind the registry no longer knows — raises.

        Args:
            node (dict): The action node blob (its ``config`` is mutated in place when healed).

        Raises:
            SearchBlobNormalizationError: The (family, kind) is unregistered or the config is broken
                beyond stale-key stripping.
        """
        family, kind = node["family"], node["kind"]
        node_id = node.get("id", f"{family}/{kind}")

        # 1. Resolve the current class — a removed kind genuinely cannot be migrated (fail loud).
        try:
            config_model = NodeRegistry.get(family, kind).Config
        except KeyError as exc:
            raise SearchBlobNormalizationError(
                f"search node '{node_id}' references a kind the engine no longer knows "
                f"({family}/{kind}) — re-save the search blob from a current default to repair"
            ) from exc

        config = node.get("config") or {}

        # 2. Validate against the current model. Clean → nothing to heal (leave config verbatim).
        try:
            config_model.model_validate(config)
            return
        except ValidationError as exc:
            stale = cls.__extra_forbidden_keys(exc)
            # 2a. A non-extra fault (wrong type, missing required) is a genuinely broken config.
            if not stale:
                raise SearchBlobNormalizationError(
                    f"search node '{node_id}' ({family}/{kind}) has an invalid config that cannot "
                    f"be auto-healed — re-save the search blob to repair (cause: {exc})"
                ) from exc

        # 3. Registry drift — strip the stale top-level keys and re-validate; a residual fault means
        #    the config is broken beyond drift and must be surfaced, never silently mangled.
        pruned = {key: value for key, value in config.items() if key not in stale}
        try:
            config_model.model_validate(pruned)
        except ValidationError as exc:
            raise SearchBlobNormalizationError(
                f"search node '{node_id}' ({family}/{kind}) config is invalid beyond stale-field "
                f"drift — re-save the search blob to repair (cause: {exc})"
            ) from exc
        cls.logger.warning(
            f"Healed stored search node '{node_id}' ({family}/{kind}): dropped stale config "
            f"field(s) {sorted(stale)} no longer known to the current engine"
        )
        node["config"] = pruned

    @staticmethod
    def __extra_forbidden_keys(exc: ValidationError) -> set[str]:
        """
        The set of TOP-LEVEL config keys a validation error rejected as extra (registry drift).

        Returns a non-empty set ONLY when EVERY error is an ``extra_forbidden`` on a top-level key,
        so a config that also fails for another reason (a type error alongside a stale key) is not
        mistaken for pure drift and healed away.

        Args:
            exc (ValidationError): The error raised validating the stored config.

        Returns:
            set[str]: The stale top-level keys to strip, or an empty set when the error is not pure
            top-level drift.
        """
        keys: set[str] = set()
        for error in exc.errors():
            location = error.get("loc") or ()
            if error.get("type") != _EXTRA_FORBIDDEN or len(location) != 1:
                return set()
            keys.add(str(location[0]))
        return keys


__all__ = ["SearchBlobNormalizer", "SearchBlobNormalizationError"]
