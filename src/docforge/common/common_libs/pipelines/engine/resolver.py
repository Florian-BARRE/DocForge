# ====== Code Summary ======
# Resolver — the intelligence behind the "intelligent context": given a node's declared bindings, it
# locates each value (resolve), checks it exists / is non-None / is the right shape (verify), and
# builds the node's typed Input (inject). It also resolves the node's required capabilities up the
# registry chain. Every failure is a precise ResolutionError that names the field, the consumer node,
# the expected source, and the reason — so the feedback tree pinpoints exactly what was missing.
# Two axes: input bindings resolve HORIZONTALLY (sibling outputs / run input); capabilities resolve
# VERTICALLY (up the ancestor registry).

# ====== Third-Party Library Imports ======
from loggerplusplus import loggerplusplus

# ====== Internal Project Imports ======
from ..base import (
    AbstractNode,
    FromParent,
    FromRunInput,
    FromSibling,
    NodeInput,
    NodeOutput,
    ResolutionError,
    ServiceRegistry,
    Source,
    input_bindings,
)


class Resolver:
    """
    Static resolver — builds a node's typed Input and resolves its required capabilities.

    Stateless: every method takes exactly the registries it reads, so it is trivially testable and
    the engine stays the only owner of run state.
    """

    logger = loggerplusplus.bind(identifier="Resolver")

    def __new__(cls, *args: object, **kwargs: object) -> None:  # type: ignore[misc]
        """Block instantiation — this is a static-only helper class."""
        raise TypeError("Resolver is a static-only class and cannot be instantiated.")

    @classmethod
    def build_input(
        cls,
        node: "AbstractNode",
        run_input: NodeInput,
        parent_input: NodeInput,
        siblings: dict[str, "NodeOutput"],
    ) -> NodeInput:
        """
        Resolve, verify, and inject a node's typed Input from its declared bindings.

        Args:
            node (AbstractNode): The node whose Input is being assembled.
            run_input (NodeInput): The pipeline run input (source of ``FromRunInput`` bindings).
            parent_input (NodeInput): The parent composite's resolved input (``FromParent``).
            siblings (dict[str, NodeOutput]): Outputs of the already-run siblings (``FromSibling``).

        Returns:
            NodeInput: The node's validated Input instance.

        Raises:
            ResolutionError: When a required binding cannot be satisfied, or the Input fails to
                validate against its declared types.
        """
        # 1. No bindings -> the Input is either empty or fully defaulted.
        bindings = input_bindings(node.Input)
        if not bindings:
            return node.Input()

        # 2. Resolve + verify each declared field.
        values: dict[str, object] = {}
        for field_name, source in bindings.items():
            values[field_name] = cls._resolve_field(
                node, field_name, source, run_input, parent_input, siblings
            )

        # 3. Inject — Pydantic validates the assembled values against the declared field types.
        try:
            return node.Input(**values)
        except Exception as exc:  # validation failure = a contract violation, surfaced precisely
            cls.logger.debug(f"Input validation failed for node {node.key!r}: {exc}")
            raise ResolutionError(
                f"Input {node.Input.__name__!r} of node {node.key!r} failed validation: {exc}",
                node_key=node.key,
                code="input_validation_failed",
                cause=exc,
            ) from exc

    @classmethod
    def resolve_services(
        cls, node: "AbstractNode", registry: "ServiceRegistry"
    ) -> dict[str, object]:
        """
        Resolve every service a node requires, walking up the ancestor registry chain.

        Args:
            node (AbstractNode): The node whose ``REQUIRES`` is being resolved.
            registry (ServiceRegistry): The registry visible at the node's level.

        Returns:
            dict[str, object]: The resolved services (exactly the node's ``REQUIRES``).

        Raises:
            ResolutionError: When a required service is provided by no level.
        """
        items: dict[str, object] = {}
        for ref in node.REQUIRES:
            value = registry.resolve(ref.name)
            if value is None:
                cls.logger.debug(
                    f"Service {ref.name!r} unresolved for node {node.key!r} (no ancestor provides it)."
                )
                raise ResolutionError(
                    f"Node {node.key!r} requires service {ref.name!r}, "
                    f"which no ancestor level provides.",
                    node_key=node.key,
                    code="service_unresolved",
                    context={"service": ref.name},
                )
            items[ref.name] = value
        return items

    @classmethod
    def _resolve_field(
        cls,
        node: "AbstractNode",
        field_name: str,
        source: Source,
        run_input: NodeInput,
        parent_input: NodeInput,
        siblings: dict[str, "NodeOutput"],
    ) -> object:
        """
        Resolve and verify a single bound field.

        Args:
            node (AbstractNode): The consuming node (for precise error attribution).
            field_name (str): The Input field being resolved.
            source (Source): The declared binding.
            run_input (NodeInput): The pipeline run input.
            parent_input (NodeInput): The parent composite's resolved input.
            siblings (dict[str, NodeOutput]): Outputs of already-run siblings.

        Returns:
            object: The resolved value (may be None when the binding is optional).

        Raises:
            ResolutionError: When a required value is missing or None.
        """
        # 1. Locate the value according to the binding kind (sibling / parent / run input).
        if isinstance(source, FromSibling):
            value = cls._from_sibling(node, field_name, source, siblings)
        elif isinstance(source, FromParent):
            field = source.field or field_name
            value = getattr(parent_input, field, None)
        elif isinstance(source, FromRunInput):
            field = source.field or field_name
            value = getattr(run_input, field, None)
        else:  # unknown Source subtype — treat as unresolved
            value = None

        # 2. Verify presence for a required binding.
        if value is None and source.required:
            cls.logger.debug(
                f"Binding {field_name!r} of node {node.key!r} unresolved "
                f"(source {type(source).__name__})."
            )
            raise ResolutionError(
                f"{node.Input.__name__}.{field_name} (node {node.key!r}) is required but "
                f"resolved to None from its declared source.",
                node_key=node.key,
                code="binding_unresolved",
                context={"field": field_name, "source": type(source).__name__},
            )
        return value

    @classmethod
    def _from_sibling(
        cls,
        node: "AbstractNode",
        field_name: str,
        source: FromSibling,
        siblings: dict[str, "NodeOutput"],
    ) -> object:
        """
        Resolve a ``FromSibling`` binding against the produced-siblings registry.

        Args:
            node (AbstractNode): The consuming node.
            field_name (str): The Input field being resolved.
            source (FromSibling): The sibling binding.
            siblings (dict[str, NodeOutput]): Outputs of already-run siblings.

        Returns:
            object: The whole sibling output, or one of its attributes when ``field`` is set.

        Raises:
            ResolutionError: When the producer sibling has not produced an output.
        """
        if source.producer not in siblings:
            cls.logger.debug(
                f"Producer {source.producer!r} has no output for binding {field_name!r} "
                f"of node {node.key!r}."
            )
            raise ResolutionError(
                f"{node.Input.__name__}.{field_name} (node {node.key!r}) consumes the output of "
                f"sibling {source.producer!r}, which has produced nothing (not run / skipped).",
                node_key=node.key,
                code="producer_missing",
                context={"field": field_name, "producer": source.producer},
            )
        output = siblings[source.producer]
        return getattr(output, source.field) if source.field else output


__all__ = ["Resolver"]
