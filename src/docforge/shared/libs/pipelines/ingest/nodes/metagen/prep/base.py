# ====== Code Summary ======
# BaseMetagenPrep — the shared machinery of the two metagen PREP nodes (document / chunk scope). A
# prep node does the LOUD, pre-spend half of what the old monolithic metagen node did: resolve the
# node's TARGETS against the contract (an unknown / non-generated / duplicated target is a config
# error and MUST fail before any model call), then group the targets per the grouping knob and emit
# ONE GenerationRequest per group — the structured-output call fully described, ready for a structgen
# chain to fulfil. It performs NO model call: that is the structgen family's job downstream. It reuses
# BaseMetagenNode's target resolution and document-view helpers unchanged (the prep is the loud front
# half of the very same node), overriding nothing that touches an endpoint.

# ====== Internal Project Imports ======
from shared_libs.pipelines.nodes.openai_compat import EndpointReachability
from shared_libs.public_models import GenerationField, GenerationRequest

# ====== Local Project Imports ======
from ..base import BaseMetagenNode, MetagenGrouping, ResolvedTarget
from .config import MetagenPrepConfig


class BaseMetagenPrep(BaseMetagenNode):
    """Abstract metagen prep — resolves targets loudly and emits one GenerationRequest per call group.

    Children decide the text source and the scope (document view + chunk_id=None, or per-chunk
    enriched text). The heavy target resolution and document-view helpers are inherited from
    BaseMetagenNode; this base only turns resolved targets into request artefacts (no model call).
    """

    async def preflight(self) -> None:
        """Verify the metagen default endpoint is reachable before any spend.

        The structured-output call itself lives on the downstream structgen chain, but the DEFAULT
        endpoint every request inherits lives on THIS prep's config — so a wrong/unreachable default
        ``base_url`` would only surface at metagen time, after the earlier stages spent. The prep is
        the metagen ladder's provider anchor, so probing its default endpoint here is what makes the
        reachability sweep catch it (the structgen chain head carries an empty override and inherits
        the request's endpoint at run time, which no preflight can see). A config whose default
        endpoint is empty (every field bound to its own per-target override) has nothing to probe
        here and is skipped, matching the structgen head's own empty-override guard.
        """
        config: MetagenPrepConfig = self.config
        if not config.base_url:
            return
        await EndpointReachability.check(
            node_kind=self.KIND,
            base_url=config.base_url,
            api_key=config.api_key,
            timeout_seconds=config.preflight_timeout_seconds,
        )

    def _build_requests(
        self, text: str, chunk_id: str | None, targets: list[ResolvedTarget], id_prefix: str
    ) -> list[GenerationRequest]:
        """
        Group the resolved targets per the grouping knob and emit one request per group.

        Applies the grouping knob (combined = one call per endpoint, per_field = one call per
        field) but emits each call group as a GenerationRequest artefact instead of running it —
        the structgen chain in the ForEach body runs them.

        Args:
            text (str): The text every request in this batch extracts from.
            chunk_id (str | None): The chunk the values will belong to (None for document scope).
            targets (list[ResolvedTarget]): The resolved fields to fill.
            id_prefix (str): Stable prefix for the request ids (unique per text source).

        Returns:
            list[GenerationRequest]: One request per call group, in stable order.
        """
        config: MetagenPrepConfig = self.config

        # 1. The call groups: per endpoint in combined mode, one per field in per_field mode.
        groups: dict[tuple[str, ...], list[ResolvedTarget]] = {}
        for index, target in enumerate(targets):
            key: tuple[str, ...] = (
                target.endpoint.base_url,
                target.endpoint.api_key,
                target.endpoint.model,
            )
            if config.grouping == MetagenGrouping.PER_FIELD:
                key = (*key, str(index))
            groups.setdefault(key, []).append(target)

        # 2. One request per group — the primary endpoint is the group's shared endpoint.
        requests: list[GenerationRequest] = []
        for group_index, group in enumerate(groups.values()):
            requests.append(
                GenerationRequest(
                    request_id=f"{id_prefix}#{group_index}",
                    chunk_id=chunk_id,
                    system_prompt=config.system_prompt,
                    text=text,
                    fields=[
                        GenerationField(spec=target.spec, instruction=target.instruction)
                        for target in group
                    ],
                    endpoint=group[0].endpoint,
                    temperature=config.temperature,
                    max_tokens=config.max_tokens,
                )
            )
        return requests


__all__ = ["BaseMetagenPrep"]
