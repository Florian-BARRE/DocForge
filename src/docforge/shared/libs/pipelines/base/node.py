# ====== Code Summary ======
# The homogeneous atom of the pipeline graph.
#
# AbstractNode is what every brick inherits: a stable KIND, human-facing self-description
# metadata, a declared error policy, a ready-to-use self.logger (LoggerClass), and a describe()
# that feeds the backend-driven UI. Two shapes specialise it:
#   - ActionNode: a leaf that uses a provider/brick. It pins three Pydantic faces —
#       Config   (static, the ONLY thing serialised into the pipeline blob),
#       Consumes (typed input slots), Produces (typed output artefacts).
#     It takes its Config at __init__, receives live capabilities later via bind() (the
#     non-serialised seam), and runs.
#   - Group (defined separately): a sub-graph of child nodes wired by transitions.
#
# The strict interface is enforced at class-definition time: a concrete ActionNode that forgets
# KIND / NAME / SUMMARY / Config / Consumes / Produces fails fast with a clear TypeError.

# ====== Standard Library Imports ======
import inspect
from abc import ABC, abstractmethod
from typing import Any

# ====== Third-Party Library Imports ======
from loggerplusplus import LoggerClass
from pydantic import BaseModel

# ====== Local Project Imports ======
from .describe import IoSlot, NodeDescription
from .enums import NodeType
from .errors import ErrorPolicy
from .io import NodeInput, NodeOutput, ScoredOutput


class AbstractNode(ABC, LoggerClass):
    """
    Base class shared by every node in the graph (action leaves and groups alike).

    Carries the identity + self-description contract, and equips every node with a ready-to-use
    ``self.logger`` (via LoggerClass). Concrete subclasses set the class-level metadata; instances
    carry a graph-unique ``id``.

    Attributes:
        KIND (str): Stable registry identifier (e.g. ``"mistral"``, ``"docling"``).
        NODE_TYPE (NodeType): ``ACTION`` or ``GROUP``.
        NAME (str): Human label surfaced in the UI.
        SUMMARY (str): One-line statement of what the node is for.
        HOW_IT_WORKS (str | None): Optional longer explanation for the UI.
        ERROR_POLICY (ErrorPolicy): The node's failure stance.
        UNIQUE_IN_GRAPH (bool): True when the node is meant to appear AT MOST ONCE per graph
            (structural utilities like admission). Providers stay False — chains repeat them.
        SELECTABLE (bool): True when a user may pick this node as a stage METHOD from the palette.
            Internal wiring nodes a stage builder emits automatically (prep/apply/skip terminals)
            set it False: the discovery palette hides them, yet they stay registered + describable.
        SWITCH_FIELDS (dict): Output fields meant for ``when_equals`` routing with their closed
            value sets (a classifier declares them; empty for everything else).
    """

    KIND: str
    NODE_TYPE: NodeType
    NAME: str
    SUMMARY: str
    HOW_IT_WORKS: str | None = None
    ERROR_POLICY: ErrorPolicy = ErrorPolicy.FAIL
    UNIQUE_IN_GRAPH: bool = False
    SELECTABLE: bool = True
    SWITCH_FIELDS: dict[str, list[str]] = {}

    def __init__(self, id: str) -> None:
        """
        Args:
            id (str): Graph-unique identifier this node is wired under.
        """
        LoggerClass.__init__(self)
        self.id = id

    @classmethod
    @abstractmethod
    def describe(cls) -> NodeDescription:
        """Return the UI-facing self-description of this node (and its children, if a group)."""
        ...


class ActionNode(AbstractNode, ABC):
    """
    A leaf node that performs work through a provider/brick.

    Pins three Pydantic faces — Config / Consumes / Produces — and follows a two-phase
    construction: ``__init__(id, config)`` binds the serialised config, then ``bind(capabilities)``
    injects live, non-serialised capabilities (clients, device, secrets) before the engine runs
    it. Only Config ever travels in the stored pipeline blob.

    Attributes:
        Config (type[BaseModel]): Static configuration model (serialised).
        Consumes (type[NodeInput]): Typed input slots the node needs to run.
        Produces (type[NodeOutput]): Typed artefacts the node emits.
    """

    NODE_TYPE = NodeType.ACTION
    Config: type[BaseModel]
    Consumes: type[NodeInput]
    Produces: type[NodeOutput]

    def __init__(self, id: str, config: BaseModel) -> None:
        """
        Args:
            id (str): Graph-unique identifier this node is wired under.
            config (BaseModel): An instance of this class's ``Config`` model.
        """
        super().__init__(id)
        self.config = config
        # Live capabilities are injected post-construction; never serialised.
        self._capabilities: Any | None = None

    def __init_subclass__(cls, **kwargs: object) -> None:
        """Enforce the strict interface on concrete (instantiable) action nodes only."""
        super().__init_subclass__(**kwargs)
        # 1. Abstract mid-layers are allowed to leave members unset.
        if inspect.isabstract(cls):
            return
        # 2. A concrete node missing any required member is a definition-time error.
        required = ("KIND", "NAME", "SUMMARY", "Config", "Consumes", "Produces")
        missing = [name for name in required if getattr(cls, name, None) is None]
        if missing:
            raise TypeError(
                f"ActionNode '{cls.__name__}' is missing required interface members: "
                f"{', '.join(missing)}"
            )

        # 3. The Config face must be a NodeConfig (extra="forbid"): a typo in a stored blob must
        #    fail the build loudly, never be silently ignored.
        from .io import NodeConfig  # local import — io.py must not depend on node.py

        if not issubclass(cls.Config, NodeConfig):
            raise TypeError(
                f"ActionNode '{cls.__name__}' Config must subclass NodeConfig "
                f"(got {cls.Config.__name__})"
            )

        # 4. Every CONSUMES/PRODUCES slot must be a plain artefact class or list[artefact class]
        #    (no unions/other generics), so describe() can name it and the validator can compare it.
        from .slots import SlotTypes  # local import — slots.py must stay dependency-free

        for face_name in ("Consumes", "Produces"):
            face: type[BaseModel] = getattr(cls, face_name)
            for slot_name, field_info in face.model_fields.items():
                element, _is_list = SlotTypes.element(field_info.annotation)
                if element is None:
                    raise TypeError(
                        f"ActionNode '{cls.__name__}' {face_name} slot '{slot_name}' must be a plain "
                        f"artefact class or list[artefact class], got {field_info.annotation!r}"
                    )

    def bind(self, capabilities: Any) -> None:
        """
        Inject live capabilities after construction — the non-serialised seam.

        Args:
            capabilities (Any): Resolved capabilities (clients, device, per-collection secrets).
        """
        self._capabilities = capabilities

    async def preflight(self) -> None:
        """
        Optional reachability/credential check run after build, before the first spend.

        Providers that call an external endpoint override it to fail fast on an unreachable URL
        or rejected credentials. Reads ``self.config`` (the per-collection URL + secret) — no
        capabilities needed. Most nodes (local RapidOCR, docling, chunkers…) never override it and
        keep this no-op, so the runner's preflight sweep costs them nothing.

        Raises:
            Exception: A provider override raises when its endpoint is unreachable or its
                credentials are rejected. The runner collects the failure and aborts the run
                before any bytes are read or stored.
        """
        return None

    @classmethod
    def describe(cls) -> NodeDescription:
        """
        Build this node's UI-facing description from its three Pydantic faces.

        Returns:
            NodeDescription: kind/labels + the ConfigModel JSON Schema + typed I/O slots.
        """
        from .slots import SlotTypes  # local import — slots.py must stay dependency-free

        consumes = [
            IoSlot(
                name=name,
                artefact_type=SlotTypes.label(field_info.annotation),
                description=field_info.description,
            )
            for name, field_info in cls.Consumes.model_fields.items()
        ]
        produces = [
            IoSlot(
                name=name,
                artefact_type=SlotTypes.label(field_info.annotation),
                description=field_info.description,
            )
            for name, field_info in cls.Produces.model_fields.items()
        ]
        return NodeDescription(
            kind=cls.KIND,
            node_type=cls.NODE_TYPE,
            name=cls.NAME,
            summary=cls.SUMMARY,
            how_it_works=cls.HOW_IT_WORKS,
            config_schema=cls.Config.model_json_schema(),
            consumes=consumes,
            produces=produces,
            error_policy=cls.ERROR_POLICY,
            unique_in_graph=cls.UNIQUE_IN_GRAPH,
            selectable=cls.SELECTABLE,
            scored=issubclass(cls.Produces, ScoredOutput),
            switch_fields=dict(cls.SWITCH_FIELDS),
        )

    @abstractmethod
    async def run(self, data: NodeInput) -> NodeOutput:
        """
        Execute the node against its resolved input and return its output.

        Args:
            data (NodeInput): An instance of this class's ``Consumes`` model, resolved by the
                engine from the node's bindings.

        Returns:
            NodeOutput: An instance of this class's ``Produces`` model.
        """
        ...


__all__ = ["AbstractNode", "ActionNode"]
