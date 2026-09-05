# ====== Code Summary ======
# PaletteScopeValidator — the palette-scope contract, expressed on a BUILT graph and shared by every
# write boundary. A pipeline kind (ingest / search) is assembled from a FIXED set of families, and a
# shared family (deliver) is further scoped to that kind's own terminal kind via FAMILY_KINDS. This
# validator turns that palette definition into a fail-fast structural check: every action node in the
# graph (nested groups and foreach bodies included) must carry a (family, kind) the target pipeline's
# palette actually offers. It rejects a genuinely FOREIGN kind — a search kind in an ingest graph, or
# vice-versa — while ADMITTING the internal wiring kinds (prep/apply/skip/keep_raw, SELECTABLE=False)
# that legitimately appear in a valid built graph: the allowed set is "every registered kind of every
# family the pipeline is built from", not just the selectable palette cards. Kept in shared_libs so
# both the app write-time validators (→ HTTP 422) and the import restore apply the exact same rule.

# ====== Third-Party Library Imports ======
from loggerplusplus import loggerplusplus

# ====== Internal Project Imports ======
from shared_libs.pipelines.base import ActionNode, ForEach, Group
from shared_libs.pipelines.registry import NodeRegistry

# ====== Local Project Imports ======
from .issues import ValidationCode, ValidationIssue


class PaletteScopeValidator:
    """
    Static check that every node of a built graph belongs to a pipeline kind's palette.

    The allowed set is resolved from the pipeline facade's ``FAMILIES`` (the families it is built
    from) and its ``FAMILY_KINDS`` allowlist (the per-family kind scoping for SHARED families such
    as ``deliver``). A family NOT in ``FAMILY_KINDS`` admits ALL its registered kinds — selectable
    palette methods AND the internal wiring kinds a stage builder emits — so a valid built graph is
    never rejected for its own scaffolding; only a genuinely foreign kind is.
    """

    logger = loggerplusplus.bind(identifier="PaletteScopeValidator")

    def __new__(cls, *args: object, **kwargs: object) -> None:
        raise TypeError("PaletteScopeValidator is a static-only class and cannot be instantiated.")

    @classmethod
    def resolve(
        cls, families: tuple[str, ...] | list[str], family_kinds: dict[str, set[str]]
    ) -> dict[str, set[str]]:
        """
        Resolve a pipeline's allowed (family → kinds) map from its palette definition.

        For each registered family the pipeline is built from, the allowed kinds are the
        ``family_kinds`` allowlist when one is declared (shared families like ``deliver``), else
        EVERY kind registered in that family — which deliberately includes the ``SELECTABLE=False``
        internal wiring kinds, since those legitimately appear in a valid built graph.

        Args:
            families (tuple[str, ...] | list[str]): The families the pipeline is assembled from.
            family_kinds (dict[str, set[str]]): Per-family kind allowlist for shared families.

        Returns:
            dict[str, set[str]]: Family → the set of kinds a valid graph of this pipeline may use.
        """
        # 1. One entry per registered family; a scoped family uses its allowlist, the rest all kinds.
        allowed: dict[str, set[str]] = {}
        registered = set(NodeRegistry.families())
        for family in families:
            if family not in registered:
                continue
            scoped = family_kinds.get(family)
            allowed[family] = set(scoped) if scoped is not None else set(NodeRegistry.kinds(family))
        return allowed

    @classmethod
    def validate(cls, root: Group, allowed: dict[str, set[str]]) -> list[ValidationIssue]:
        """
        Collect every action node whose (family, kind) is outside the allowed palette.

        Args:
            root (Group): The built graph to check (walked recursively, foreach bodies included).
            allowed (dict[str, set[str]]): Family → allowed kinds (see ``resolve``).

        Returns:
            list[ValidationIssue]: One ``KIND_NOT_IN_PALETTE`` issue per foreign node (empty when
            every node belongs to the pipeline's palette).
        """
        issues: list[ValidationIssue] = []

        # 1. Walk the full tree; each action node's family is its registration key (reverse lookup).
        def walk(group: Group) -> None:
            location = f"group '{group.id}'"
            for child in group.children:
                if isinstance(child, ActionNode):
                    family = NodeRegistry.family_of(type(child))
                    if family is None or child.KIND not in allowed.get(family, set()):
                        label = f"{family}/{child.KIND}" if family else child.KIND
                        issues.append(
                            ValidationIssue(
                                code=ValidationCode.KIND_NOT_IN_PALETTE,
                                location=f"{location} / node '{child.id}'",
                                message=(
                                    f"node kind '{label}' does not belong to this pipeline's "
                                    f"palette"
                                ),
                            )
                        )
                elif isinstance(child, Group):
                    walk(child)
                elif isinstance(child, ForEach):
                    walk(child.body)

        walk(root)
        return issues


__all__ = ["PaletteScopeValidator"]
