# ====== Code Summary ======
# Self-description of the GRAPH MECHANICS — the vocabulary the UI composes edges with, served at
# the same level as the node palette. Nodes describe themselves via describe(); this module makes
# the transitions (conditions), the data wiring (binding sources), the containers (foreach/group)
# and the error policies describe themselves too — AUTO-DERIVED from the Pydantic models and
# their docstrings, so adding a condition in base/transition.py surfaces it in the UI with zero
# extra code: its kind, labels and params form all come from the class itself.

# ====== Standard Library Imports ======
import inspect
import re
from typing import Any, get_args

# ====== Third-Party Library Imports ======
from pydantic import BaseModel, Field

# ====== Internal Project Imports ======
from shared_libs.pipelines.base import Binding, Condition, ErrorPolicy, ForEach, Group
from shared_libs.pipelines.build import GroupNodeBlob
from shared_libs.pipelines.build.blob import ForEachNodeBlob
from shared_libs.pipelines.edit.operations import EditOperation


class MechanicCard(BaseModel):
    """
    UI-facing description of one graph-mechanic variant (a condition, a binding source, …).

    The mechanics counterpart of NodeDescription: the UI renders its choice lists and parameter
    forms from these cards exactly like it renders node cards and config forms.

    Attributes:
        kind (str): Stable discriminator value (e.g. ``"score_below"``, ``"run"``).
        name (str): Human label (the model class name).
        summary (str): One-line statement of what the variant does.
        how_it_works (str | None): Optional longer explanation (docstring body).
        discriminator (str | None): Name of the tag field the client must send to select this
            variant (e.g. ``"op"`` for an edit operation, ``"action"`` for a stage action), so a
            payload is ``{<discriminator>: <kind>, **params}``. Derived from the source union's
            ``Field(discriminator=…)`` — ``None`` for cards not built from a discriminated union
            (containers, error policies), which a client never sends as a tagged payload.
        params_schema (dict): JSON Schema of the variant's editable parameters (discriminator
            removed) — drives the parameter form, like a node's config_schema.
    """

    kind: str
    name: str
    summary: str
    how_it_works: str | None = None
    discriminator: str | None = None
    params_schema: dict[str, Any] = Field(default_factory=dict)


class MechanicsDescription(BaseModel):
    """
    The full vocabulary of graph structure — everything the UI needs to build edges and loops.

    Attributes:
        conditions (list[MechanicCard]): Every transition gate (the Condition union).
        condition_priority (list[str]): Condition kinds by decreasing specificity — when several
            outgoing edges match, the engine follows the most specific one (quality escalation
            beats value routing beats plain sequence).
        binding_sources (list[MechanicCard]): Every data-wiring source (the Binding union).
        containers (list[MechanicCard]): The structural nodes (foreach, group) and their knobs.
        error_policies (list[MechanicCard]): Every per-node failure stance.
        edit_operations (list[MechanicCard]): Every graph-mutation the ``/edit`` endpoint accepts
            (the EditOperation union) — one card per ``operations[]`` payload, so a client composes
            them from the discriminator + params_schema instead of guessing. Pipeline-agnostic.
        stage_actions (list[MechanicCard]): Every stage-rail action the ``/stages/apply`` endpoint
            accepts (the StageAction union) — one card per ``action`` payload. Empty for a pipeline
            with no stage rail (the stage layer is ingest-coupled today).
    """

    conditions: list[MechanicCard]
    condition_priority: list[str]
    binding_sources: list[MechanicCard]
    containers: list[MechanicCard]
    error_policies: list[MechanicCard]
    edit_operations: list[MechanicCard] = Field(default_factory=list)
    stage_actions: list[MechanicCard] = Field(default_factory=list)


class GraphMechanics:
    """Static builder of the mechanics description — derived from the base models, never typed twice."""

    def __new__(cls, *args: object, **kwargs: object) -> None:
        raise TypeError("GraphMechanics is a static-only class and cannot be instantiated.")

    @staticmethod
    def __split_doc(doc: str | None) -> tuple[str, str | None]:
        """Split a docstring into (one-line summary, remaining explanation or None)."""
        text = inspect.cleandoc(doc or "")
        parts = text.split("\n\n", 1)
        summary = parts[0].replace("\n", " ").strip()
        rest = parts[1].strip() if len(parts) > 1 else None
        return summary, rest

    @classmethod
    def __card_from_model(cls, model: type[BaseModel], discriminator: str) -> MechanicCard:
        """Build one variant's card from its Pydantic model: kind, docstring labels, params form."""
        # 1. The discriminator's default IS the variant's stable kind.
        kind = str(model.model_fields[discriminator].default)

        # 2. The params form is the model's schema minus the discriminator (it is not a knob).
        schema = model.model_json_schema()
        schema.get("properties", {}).pop(discriminator, None)
        if discriminator in schema.get("required", []):
            schema["required"] = [r for r in schema["required"] if r != discriminator]

        # 3. Labels come from the class itself.
        summary, rest = cls.__split_doc(model.__doc__)
        return MechanicCard(
            kind=kind,
            name=model.__name__,
            summary=summary,
            how_it_works=rest,
            discriminator=discriminator,
            params_schema=schema,
        )

    @staticmethod
    def __union_members(alias: Any) -> tuple[type[BaseModel], ...]:
        """Return the member models of a `type X = Annotated[A | B | …, Field(...)]` alias."""
        return get_args(get_args(alias.__value__)[0])

    @staticmethod
    def __union_discriminator(alias: Any) -> str:
        """Read the tag field name from a `type X = Annotated[…, Field(discriminator=…)]` alias.

        Sourced from the union's own ``Field(discriminator=…)`` metadata so renaming the tag (or
        adding a new union) needs no change here — the surfaced discriminator follows the source.
        """
        return get_args(alias.__value__)[1].discriminator

    @staticmethod
    def __root_schema(model: type[BaseModel]) -> dict[str, Any]:
        """A model's JSON Schema with its root inlined — recursive models emit a bare $ref root."""
        schema = model.model_json_schema()
        if "$ref" in schema:
            root = schema["$ref"].split("/")[-1]
            defs = schema.get("$defs", {})
            schema = {**defs.get(root, {}), "$defs": defs}
        return schema

    @classmethod
    def __error_policy_cards(cls) -> list[MechanicCard]:
        """One card per ErrorPolicy value, its summary parsed from the enum's Attributes doc."""
        doc = inspect.cleandoc(ErrorPolicy.__doc__ or "")
        cards = []
        for policy in ErrorPolicy:
            # Grab "VALUE: explanation…" up to the next attribute or the end of the docstring.
            match = re.search(rf"{policy.name}: (.+?)(?=\n\s*[A-Z_]+:|\Z)", doc, re.DOTALL)
            summary = re.sub(r"\s+", " ", match.group(1)).strip() if match else ""
            cards.append(MechanicCard(kind=str(policy), name=policy.name, summary=summary))
        return cards

    @classmethod
    def __container_cards(cls) -> list[MechanicCard]:
        """The structural nodes: their labels from the live classes, their knobs from the blobs."""
        # 1. ForEach: knobs = over / item_field / max_concurrency; the body is a nested graph,
        #    not a parameter — the UI builds it like any container.
        foreach_schema = cls.__root_schema(ForEachNodeBlob)
        for key in ("node_type", "id", "body"):
            foreach_schema.get("properties", {}).pop(key, None)
        foreach_schema["required"] = [
            r for r in foreach_schema.get("required", []) if r not in ("id", "body")
        ]
        _, foreach_rest = cls.__split_doc(ForEach.__doc__)
        cards = [
            MechanicCard(
                kind=ForEach.KIND,
                name=ForEach.NAME,
                summary=ForEach.SUMMARY,
                how_it_works=foreach_rest,
                params_schema=foreach_schema,
            )
        ]

        # 2. Group: a named sub-graph; no knobs beyond its id and content.
        _, group_rest = cls.__split_doc(Group.__doc__)
        cards.append(
            MechanicCard(
                kind=Group.KIND,
                name=Group.NAME,
                summary=Group.SUMMARY,
                how_it_works=group_rest,
                params_schema=cls.__root_schema(GroupNodeBlob),
            )
        )
        return cards

    @classmethod
    def union_cards(cls, alias: Any) -> list[MechanicCard]:
        """
        Describe every member of a discriminated-union alias, one card per variant.

        The public seam a pipeline owner uses to surface its OWN vocabulary (e.g. the ingest
        stage-action union) without this generic module importing that pipeline's models — the
        caller passes the alias, the derivation (members AND discriminator name) stays
        single-sourced here.

        Args:
            alias (Any): A ``type X = Annotated[A | B | …, Field(discriminator=…)]`` alias — the
                tag field name is read from its own ``Field(discriminator=…)`` metadata.

        Returns:
            list[MechanicCard]: One card per union member — its tag, the discriminator key to send
            it under, labels and params form.
        """
        discriminator = cls.__union_discriminator(alias)
        return [cls.__card_from_model(m, discriminator) for m in cls.__union_members(alias)]

    @classmethod
    def describe(cls, stage_actions: Any = None) -> MechanicsDescription:
        """
        Build the full mechanics vocabulary from the base models.

        Args:
            stage_actions (Any): Optional StageAction union alias — passed by a pipeline that owns
                a stage rail (ingest) so its ``/stages/apply`` vocabulary is surfaced too. Left None
                by a pipeline with no stage rail (search), keeping ``stage_actions`` empty.

        Returns:
            MechanicsDescription: Conditions (+ their priority), binding sources, containers,
            error policies, edit operations and — when a stage-action union is passed — stage
            actions; each variant with its labels and params form.
        """
        # 1. Conditions and bindings: auto-derived from their discriminated unions (members and
        #    the discriminator name both read from the alias — no tag literal duplicated here).
        conditions = cls.union_cards(Condition)
        sources = cls.union_cards(Binding)

        # 2. Priority mirrors the engine's resolution order (most specific edge wins).
        priority = ["score_below", "when_equals", "on_success", "on_failure", "always"]

        # 3. Mutation vocabularies: graph edits are pipeline-agnostic; stage actions belong to the
        #    caller that owns a stage rail (passed in to keep this generic module ingest-free).
        edit_operations = cls.union_cards(EditOperation)
        stage_action_cards = cls.union_cards(stage_actions) if stage_actions else []

        return MechanicsDescription(
            conditions=conditions,
            condition_priority=priority,
            binding_sources=sources,
            containers=cls.__container_cards(),
            error_policies=cls.__error_policy_cards(),
            edit_operations=edit_operations,
            stage_actions=stage_action_cards,
        )


__all__ = ["MechanicCard", "MechanicsDescription", "GraphMechanics"]
