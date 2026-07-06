# ====== Code Summary ======
# BaseMetagenNode — the shared machinery of the two metagen nodes (document / chunk scope):
# resolve the node's TARGETS against the contract (loudly — a target naming an unknown or
# non-generated field is a config error), group them by endpoint per the grouping knob, run the
# structured-output calls through the shared factory, and coerce every returned value to its
# contract type. Children implement run() — WHAT text is generated on and WHERE values land.

# ====== Standard Library Imports ======
from typing import Any

# ====== Third-Party Library Imports ======
from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, ConfigDict

# ====== Internal Project Imports ======
from shared_libs.pipelines.base import ActionNode
from shared_libs.pipelines.nodes.openai_compat import OpenAICompatConfig, OpenAICompatHelpers
from shared_libs.public_models import CollectionContract, FieldOrigin, FieldScope, MetadataFieldSpec

# ====== Local Project Imports ======
from .config import BaseMetagenConfig, MetagenGrouping, MetagenOnError
from .helpers import MetagenHelpers


class ResolvedTarget(BaseModel):
    """One field to generate, fully resolved: its spec, instruction and endpoint."""

    model_config = ConfigDict(extra="forbid")

    spec: MetadataFieldSpec
    instruction: str
    endpoint: OpenAICompatConfig


class BaseMetagenNode(ActionNode):
    """Abstract metagen node — children decide the text source and the value destination."""

    def __endpoint(self, base_url: str = "", api_key: str = "", model: str = "") -> OpenAICompatConfig:
        """The effective endpoint of a target — its overrides on top of the node's default."""
        config: BaseMetagenConfig = self.config
        return OpenAICompatConfig(
            base_url=base_url or config.base_url,
            api_key=api_key or config.api_key,
            model=model or config.model,
            timeout_seconds=config.timeout_seconds,
        )

    @staticmethod
    def __is_other_scope(contract: CollectionContract, field: str, scope: FieldScope) -> bool:
        """True when the field IS generated but belongs to the other scope's node."""
        return any(
            spec.field_name == field and spec.origin == FieldOrigin.GENERATED
            and spec.scope != scope
            for spec in contract.fields
        )

    def _resolve_targets(
        self, contract: CollectionContract, scope: FieldScope
    ) -> list[ResolvedTarget]:
        """
        Resolve what THIS node must generate: the contract declares, the config binds.

        Args:
            contract (CollectionContract): The collection contract (run input).
            scope (FieldScope): The node's scope (DOCUMENT or CHUNK).

        Returns:
            list[ResolvedTarget]: One resolved target per field to fill.

        Raises:
            ValueError: When a configured target names an unknown, non-generated or
                wrong-scope field — a config error must fail loudly, before any spend.
        """
        config: BaseMetagenConfig = self.config
        generated = {
            spec.field_name: spec
            for spec in contract.fields
            if spec.origin == FieldOrigin.GENERATED and spec.scope == scope
        }

        # 1. No explicit targets: every generated field of the scope, auto prompts, default LLM.
        if not config.targets:
            return [
                ResolvedTarget(
                    spec=spec,
                    instruction=MetagenHelpers.auto_prompt(spec),
                    endpoint=self.__endpoint(),
                )
                for spec in generated.values()
            ]

        # 2. Explicit targets: validate each against the contract, apply the per-field bindings;
        #    targets of the OTHER scope are simply not this node's business. A field targeted
        #    twice is a config error (last-wins would waste spend silently).
        seen: set[str] = set()
        resolved: list[ResolvedTarget] = []
        for target in config.targets:
            if target.field in seen:
                raise ValueError(
                    f"Metagen node '{self.id}': field '{target.field}' targeted more than once"
                )
            seen.add(target.field)
            spec = generated.get(target.field)
            if spec is None:
                if self.__is_other_scope(contract, target.field, scope):
                    continue
                raise ValueError(
                    f"Metagen node '{self.id}': target field '{target.field}' is not a "
                    f"GENERATED field of the contract"
                )
            resolved.append(
                ResolvedTarget(
                    spec=spec,
                    instruction=target.prompt or MetagenHelpers.auto_prompt(spec),
                    endpoint=self.__endpoint(target.base_url, target.api_key, target.model),
                )
            )
        if not resolved:
            self.logger.warning(
                f"Metagen node '{self.id}': explicit targets resolved to ZERO "
                f"{scope.value}-scope field(s) — check the targeted fields' scope"
            )
        return resolved

    async def _generate(
        self, schema: dict[str, Any], system_prompt: str, text: str, endpoint: OpenAICompatConfig
    ) -> dict[str, Any]:
        """One structured-output call (overridable hook) — the schema forces the shape."""
        config: BaseMetagenConfig = self.config
        model = OpenAICompatHelpers.chat(
            endpoint, temperature=config.temperature, max_tokens=config.max_tokens
        )
        structured = model.with_structured_output(schema)
        result = await structured.ainvoke(
            [SystemMessage(content=system_prompt), HumanMessage(content=text)]
        )
        return dict(result)

    async def _generate_values(
        self, text: str, targets: list[ResolvedTarget]
    ) -> dict[str, Any]:
        """
        Fill the targets from one text: group by endpoint (per the grouping knob), call, coerce.

        Args:
            text (str): The text the values are extracted from.
            targets (list[ResolvedTarget]): What to fill.

        Returns:
            dict: Field name → coerced value (failed/uncoercible fields absent).
        """
        config: BaseMetagenConfig = self.config

        # 1. The call groups: per endpoint in combined mode, one per field in per_field mode.
        groups: dict[tuple[str, ...], list[ResolvedTarget]] = {}
        for index, target in enumerate(targets):
            key: tuple[str, ...] = (
                target.endpoint.base_url, target.endpoint.api_key, target.endpoint.model,
            )
            if config.grouping == MetagenGrouping.PER_FIELD:
                key = (*key, str(index))
            groups.setdefault(key, []).append(target)

        # 2. One structured call per group; a failure drops the group's fields (or fails).
        values: dict[str, Any] = {}
        for group in groups.values():
            schema = MetagenHelpers.object_schema(
                [(target.spec, target.instruction) for target in group]
            )
            try:
                raw = await self._generate(schema, config.system_prompt, text, group[0].endpoint)
            except Exception as exc:
                if config.on_error == MetagenOnError.FAIL:
                    raise
                self.logger.warning(
                    f"Metagen '{self.KIND}' dropped {len(group)} field(s) "
                    f"({', '.join(t.spec.field_name for t in group)}): "
                    f"{type(exc).__name__}: {exc}"
                )
                continue
            # 3. STRICT coercion — a wrong-typed value is dropped, never stored.
            for target in group:
                coerced = MetagenHelpers.coerce(raw.get(target.spec.field_name), target.spec.field_type)
                if coerced is not None:
                    values[target.spec.field_name] = coerced
        return values

    @staticmethod
    def _document_text(texts: list[str], max_words: int) -> str:
        """Join texts into the generation view — structure kept when under the word cap."""
        joined = "\n\n".join(texts)
        words = joined.split()
        if len(words) <= max_words:
            return joined
        return " ".join(words[:max_words])


__all__ = ["BaseMetagenNode", "ResolvedTarget"]
