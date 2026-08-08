# ====== Code Summary ======
# BaseMetagenNode — the shared, model-free machinery of the metagen family: resolve the node's TARGETS
# against the contract (loudly — a target naming an unknown or non-generated field is a config error)
# and build the word-capped document view. The structured-output call itself is NOT here anymore: it
# was externalised into the generic structgen chain, so this base only does the loud, pre-spend work
# its PREP children (BaseMetagenPrep) turn into GenerationRequest artefacts.

# ====== Third-Party Library Imports ======
from pydantic import BaseModel, ConfigDict

# ====== Internal Project Imports ======
from shared_libs.pipelines.base import ActionNode
from shared_libs.pipelines.nodes.openai_compat import OpenAICompatConfig
from shared_libs.public_models import CollectionContract, FieldOrigin, FieldScope, MetadataFieldSpec

# ====== Local Project Imports ======
from .config import BaseMetagenConfig
from .helpers import MetagenHelpers


class ResolvedTarget(BaseModel):
    """One field to generate, fully resolved: its spec, instruction and endpoint."""

    model_config = ConfigDict(extra="forbid")

    spec: MetadataFieldSpec
    instruction: str
    endpoint: OpenAICompatConfig


class BaseMetagenNode(ActionNode):
    """Abstract metagen node — children decide the text source and the value destination."""

    def __endpoint(
        self, base_url: str = "", api_key: str = "", model: str = ""
    ) -> OpenAICompatConfig:
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
            spec.field_name == field
            and spec.origin == FieldOrigin.GENERATED
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
                    instruction=MetagenHelpers.auto_prompt(spec, scope),
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
                    instruction=target.prompt or MetagenHelpers.auto_prompt(spec, scope),
                    endpoint=self.__endpoint(target.base_url, target.api_key, target.model),
                )
            )
        if not resolved:
            self.logger.warning(
                f"Metagen node '{self.id}': explicit targets resolved to ZERO "
                f"{scope.value}-scope field(s) — check the targeted fields' scope"
            )
        return resolved

    @staticmethod
    def _document_text(texts: list[str], max_words: int) -> str:
        """Join texts into the generation view, keeping the HEAD and TAIL when over the word cap.

        A head-only truncation would blind a closing-summary or conclusion field to the end of the
        document; over the cap the view keeps the first and last halves, joined by an elision marker
        so the model sees both ends of the text rather than only its opening.

        Args:
            texts (list[str]): The per-chunk texts to assemble into one document view.
            max_words (int): Hard cap on the number of words handed to the model.

        Returns:
            str: The full text when under the cap, else its head + tail with the middle elided.
        """
        joined = "\n\n".join(texts)
        words = joined.split()
        if len(words) <= max_words:
            return joined
        half = max_words // 2
        return " ".join([*words[:half], "[…]", *words[-half:]])


__all__ = ["BaseMetagenNode", "ResolvedTarget"]
