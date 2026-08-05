# ====== Code Summary ======
# Central registry of node classes, grouped by family (capability: llm, ocr, vlm, embed, …).
#
# It is the SINGLE source of truth that feeds both the UI and deserialisation:
#   - kinds(family)   → the dynamic choice list for a family (auto-built from what is registered,
#                       so dropping a provider folder adds a choice with zero manual edits),
#   - get(family,kind)→ the class to instantiate when rebuilding a pipeline from its blob,
#   - catalog(family) → the palette cards (each class's describe(), no instance needed).
#
# Nodes self-register with the @NodeRegistry.register("<family>") decorator. auto_import() is
# called from a family package's __init__ so every node submodule is imported (and therefore
# registered) just by living in the folder.
#
# It lives at the pipelines top level, NOT in base/: base/ holds pure, stateless contracts, while
# this is a stateful mechanism (global store + dynamic imports) that operates on them.

# ====== Standard Library Imports ======
import importlib
import pkgutil
from collections.abc import Callable
from enum import StrEnum

# ====== Third-Party Library Imports ======
from loggerplusplus import loggerplusplus
from pydantic import BaseModel

# ====== Local Project Imports ======
from .base import AbstractNode, NodeDescription


class FamilyMode(StrEnum):
    """
    How the nodes of a family are meant to be USED together — the palette's usage semantics.

    Attributes:
        EXCLUSIVE: Pick ONE node of the family per pipeline (chunker, converter, parser, embed).
        STACKABLE: The nodes chain and ACCUMULATE — wiring order = application order
            (contextualize).
        CHAIN: Interchangeable providers meant for ESCALATION chains — same kind may repeat
            with different configs, joined back with score_below/on_failure + from_first
            (ocr, vlm, llm).
        STAGE: The complementary logic nodes of one pipeline stage — each plays a distinct,
            usually single-use role (intake, enrich, metagen).
    """

    EXCLUSIVE = "exclusive"
    STACKABLE = "stackable"
    CHAIN = "chain"
    STAGE = "stage"


class FamilyInfo(BaseModel):
    """
    UI-facing description of one family — what it is and how its nodes are meant to be used.

    Attributes:
        family (str): The registry family key.
        title (str): Human label.
        description (str): What the family does and how to use its nodes together.
        mode (FamilyMode): The usage semantics the UI adapts its editor to.
    """

    family: str
    title: str
    description: str
    mode: FamilyMode


class NodeRegistry:
    """
    Static-only registry mapping (family, kind) → node class.

    Never instantiated. All state and behaviour are class-level, so any part of the codebase
    reads the same registry.
    """

    logger = loggerplusplus.bind(identifier="NodeRegistry")
    _store: dict[str, dict[str, type[AbstractNode]]] = {}
    _family_info: dict[str, FamilyInfo] = {}

    def __new__(cls, *args: object, **kwargs: object) -> None:
        raise TypeError("NodeRegistry is a static-only class and cannot be instantiated.")

    @classmethod
    def register(cls, family: str) -> Callable[[type[AbstractNode]], type[AbstractNode]]:
        """
        Decorator registering a node class under ``family``, keyed by its ``KIND``.

        Args:
            family (str): Capability the node belongs to (e.g. ``"llm"``, ``"ocr"``).

        Returns:
            Callable: A decorator that stores the class and returns it unchanged.

        Raises:
            ValueError: If the class has no KIND, or that kind already exists in the family.
        """

        def decorator(node_class: type[AbstractNode]) -> type[AbstractNode]:
            # 1. Every registered node must carry a stable KIND.
            kind = getattr(node_class, "KIND", None)
            if not kind:
                raise ValueError(f"Cannot register {node_class.__name__}: it has no KIND.")

            # 2. Reject collisions inside the same family (fail fast).
            family_members = cls._store.setdefault(family, {})
            if kind in family_members:
                raise ValueError(
                    f"Duplicate node kind '{kind}' in family '{family}' "
                    f"(already registered by {family_members[kind].__name__})."
                )

            # 3. Store and log.
            family_members[kind] = node_class
            cls.logger.debug(f"Registered node '{kind}' in family '{family}'")
            return node_class

        return decorator

    @classmethod
    def get(cls, family: str, kind: str) -> type[AbstractNode]:
        """
        Return the node class registered under (family, kind).

        Args:
            family (str): Capability family.
            kind (str): The node's stable KIND within that family.

        Returns:
            type[AbstractNode]: The registered class.

        Raises:
            KeyError: If no node is registered for that (family, kind).
        """
        try:
            return cls._store[family][kind]
        except KeyError:
            raise KeyError(f"No node registered for family '{family}', kind '{kind}'.")

    @classmethod
    def family_of(cls, node_class: type[AbstractNode]) -> str | None:
        """
        Return the family a node class is registered under (the reverse of ``get``).

        A node stores its KIND but not its family — the family is the registration key. This
        reverse lookup lets an orchestration seam (e.g. a reachability sweep) label a built node
        instance with its family without threading the family through the graph.

        Args:
            node_class (type[AbstractNode]): The registered node class to locate.

        Returns:
            str | None: The family the class is registered under, or None when unregistered
            (structural nodes like Group/ForEach never register).
        """
        for family, members in cls._store.items():
            if node_class in members.values():
                return family
        return None

    @classmethod
    def kinds(cls, family: str) -> list[str]:
        """
        Return the available kinds for a family — the dynamic choice list for the UI.

        Args:
            family (str): Capability family.

        Returns:
            list[str]: Registered kinds (empty if the family is unknown).
        """
        return list(cls._store.get(family, {}).keys())

    @classmethod
    def families(cls) -> list[str]:
        """
        Return every registered family (capability).

        Returns:
            list[str]: The known family names.
        """
        return list(cls._store.keys())

    @classmethod
    def catalog(cls, family: str) -> list[NodeDescription]:
        """
        Return the palette cards of the SELECTABLE nodes registered in a family.

        Each card is the class's describe() — built without instantiating, so the UI can list
        the available bricks and their config schemas before anything is configured. Nodes flagged
        ``SELECTABLE = False`` (internal wiring a stage builder emits automatically — prep/apply
        nodes, fail-soft terminals) are omitted: they stay registered and reachable via ``get`` /
        ``kinds`` / ``describe``, but the discovery palette never offers them as a stage method.

        Args:
            family (str): Capability family.

        Returns:
            list[NodeDescription]: One type-card per selectable registered node.
        """
        cards = [node_class.describe() for node_class in cls._store.get(family, {}).values()]
        return [card for card in cards if card.selectable]

    @classmethod
    def register_family(cls, family: str, title: str, description: str, mode: FamilyMode) -> None:
        """
        Declare a family's UI metadata — its label and its usage semantics.

        Called once from the family package's ``__init__`` (next to auto_import), so the
        knowledge of HOW a family is meant to be used ships with the family itself.

        Args:
            family (str): The registry family key.
            title (str): Human label.
            description (str): What the family does and how its nodes combine.
            mode (FamilyMode): exclusive / stackable / chain / stage.
        """
        cls._family_info[family] = FamilyInfo(
            family=family, title=title, description=description, mode=mode
        )

    @classmethod
    def family_info(cls, family: str) -> FamilyInfo | None:
        """
        The declared metadata of a family (None when the family never declared any).

        Args:
            family (str): The registry family key.

        Returns:
            FamilyInfo | None: The family's UI metadata.
        """
        return cls._family_info.get(family)

    @classmethod
    def auto_import(cls, package_name: str) -> None:
        """
        Import every submodule of a package so its @register decorators fire.

        Call this from a family package's ``__init__`` so a node registers itself simply by
        living in the folder — no central list to maintain.

        Args:
            package_name (str): Dotted name of the package to scan (e.g. ``"pipelines.nodes.llm"``).
        """
        package = importlib.import_module(package_name)
        for module_info in pkgutil.iter_modules(package.__path__, prefix=f"{package_name}."):
            importlib.import_module(module_info.name)


__all__ = ["NodeRegistry", "FamilyInfo", "FamilyMode"]
