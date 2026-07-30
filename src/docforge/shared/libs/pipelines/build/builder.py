# ====== Code Summary ======
# Rebuilds a live pipeline (a Group of node instances) from its serialised blob. For each action
# node it looks up the registered class by (family, kind), validates the raw config against that
# class's Config model, and instantiates it; groups are rebuilt recursively. Every failure —
# malformed blob, unknown family/kind, non-action class, invalid config — raises a precise
# BuildError naming the node, so a bad pipeline never reaches the engine silently.

# ====== Standard Library Imports ======
from typing import Any

# ====== Third-Party Library Imports ======
from loggerplusplus import LoggerClass
from pydantic import ValidationError

# ====== Internal Project Imports ======
from shared_libs.pipelines.base import AbstractNode, ActionNode, ForEach, Group
from shared_libs.pipelines.registry import NodeRegistry

# ====== Local Project Imports ======
from .blob import ActionNodeBlob, ForEachNodeBlob, GroupNodeBlob, NodeBlob


class BuildError(Exception):
    """Raised when a pipeline blob cannot be turned into a live graph."""


class PipelineBuilder(LoggerClass):
    """
    Turns a serialised pipeline blob into a live Group of node instances.

    Stateless across calls; reads the NodeRegistry to resolve each node's class.
    """

    def __init__(self) -> None:
        LoggerClass.__init__(self)

    def __build_action(self, blob: ActionNodeBlob) -> ActionNode:
        """Resolve, validate and instantiate a single action node."""
        # 1. Resolve the registered class for (family, kind).
        try:
            node_class = NodeRegistry.get(blob.family, blob.kind)
        except KeyError as exc:
            self.logger.error(f"Cannot build node '{blob.id}': {exc}")
            raise BuildError(f"node '{blob.id}': {exc}") from exc

        # 2. A registered class must be an action node to carry a Config and run.
        if not issubclass(node_class, ActionNode):
            self.logger.error(
                f"Cannot build node '{blob.id}': '{blob.family}/{blob.kind}' is not an action node"
            )
            raise BuildError(
                f"node '{blob.id}': '{blob.family}/{blob.kind}' is not an action node."
            )

        # 3. Validate the raw config against the class's Config model.
        try:
            config = node_class.Config.model_validate(blob.config)
        except ValidationError as exc:
            self.logger.error(
                f"Invalid config for node '{blob.id}' ({blob.family}/{blob.kind}): {exc}"
            )
            raise BuildError(
                f"node '{blob.id}' ({blob.family}/{blob.kind}) has an invalid config: {exc}"
            ) from exc

        # 4. Instantiate the live node.
        return node_class(id=blob.id, config=config)

    def __build_node(self, blob: NodeBlob) -> AbstractNode:
        """Build a child node: an action node, a nested group, or a foreach."""
        if isinstance(blob, GroupNodeBlob):
            return self.__build_group(blob)
        if isinstance(blob, ForEachNodeBlob):
            return self.__build_foreach(blob)
        return self.__build_action(blob)

    def __build_foreach(self, blob: ForEachNodeBlob) -> ForEach:
        """Build a foreach: its per-item body is rebuilt like any group."""
        return ForEach(
            id=blob.id,
            body=self.__build_group(blob.body),
            over=blob.over,
            item_field=blob.item_field,
            max_concurrency=blob.max_concurrency,
        )

    def __build_group(self, blob: GroupNodeBlob) -> Group:
        """Build a group and its children recursively."""
        children = [self.__build_node(child) for child in blob.nodes]
        # Group's own __init__ fails fast on duplicate child ids — surface it as a BuildError so
        # every build failure is the same exception type.
        try:
            return Group(
                id=blob.id,
                children=children,
                transitions=blob.transitions,
                bindings=blob.bindings,
            )
        except ValueError as exc:
            self.logger.error(f"Cannot build group '{blob.id}': {exc}")
            raise BuildError(f"group '{blob.id}': {exc}") from exc

    def build(self, blob: GroupNodeBlob | dict[str, Any]) -> Group:
        """
        Build a live pipeline Group from its blob.

        Args:
            blob (GroupNodeBlob | dict): The serialised pipeline — a group blob or its raw dict.

        Returns:
            Group: The rebuilt graph, ready for the FlowEngine.

        Raises:
            BuildError: If the blob is malformed or any node cannot be built.
        """
        # 1. Parse a raw dict into the typed blob (precise error on a malformed blob).
        if isinstance(blob, dict):
            try:
                group_blob = GroupNodeBlob.model_validate(blob)
            except ValidationError as exc:
                self.logger.error(f"Malformed pipeline blob: {exc}")
                raise BuildError(f"malformed pipeline blob: {exc}") from exc
        else:
            group_blob = blob

        # 2. Build the graph.
        self.logger.info(f"Building pipeline '{group_blob.id}'")
        return self.__build_group(group_blob)


__all__ = ["PipelineBuilder", "BuildError"]
