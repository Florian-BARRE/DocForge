# ====== Code Summary ======
# ChainSecretCarry — keeps a provider's secret across a chain rebuild. A set_chain / set_provider /
# set_stack re-states a chain's steps; a step that OMITS its secret (api_key / password) inherits it
# from the SAME provider of the current chain at the SAME effective endpoint (SecretIdentity: same kind
# at that position, or a same-kind step at that endpoint after a reorder) BEFORE the build-safe
# completion would fill a required secret with "". A step whose endpoint CHANGED never inherits: its
# omitted secret becomes the redaction mask plus a notice, so the write path (restore_blob_secrets)
# refuses it until the secret is re-entered — the build-safe completion cannot turn it into a silent
# "". An explicit value (a new key, "" to clear, or a mask) is never touched, and a kind mismatch
# never inherits anything.

# ====== Internal Project Imports ======
from shared_libs.pipelines.blob_secrets import MASK
from shared_libs.pipelines.secret_identity import SECRET_FIELDS, ProviderRef, SecretIdentity

# ====== Local Project Imports ======
from .models import ChainStep


class ChainSecretCarry:
    """Static carry-over of omitted step secrets from the current chain to its rebuilt steps."""

    def __new__(cls, *args: object, **kwargs: object) -> None:
        raise TypeError("ChainSecretCarry is a static-only class and cannot be instantiated.")

    @staticmethod
    def __held(config: dict | None, field: str) -> bool:
        """Whether a config holds a non-empty value (a real key or a mask) for ``field``."""
        value = (config or {}).get(field)
        return isinstance(value, str) and value != ""

    @classmethod
    def carry(
        cls,
        family: str,
        current: list[ChainStep],
        proposed: list[ChainStep],
        notices: list[str],
    ) -> list[ChainStep]:
        """
        Return ``proposed`` with each omitted secret inherited from its same-provider current step.

        Args:
            family (str): The chain's registry family (resolves each kind's default endpoint).
            current (list[ChainStep]): The chain's steps before the edit (holding the live secrets).
            proposed (list[ChainStep]): The steps the action re-states.
            notices (list[str]): Appended with one re-entry notice per step whose endpoint moved.

        Returns:
            list[ChainStep]: Fresh steps (``proposed`` is never mutated).
        """
        siblings: list[ProviderRef] = [(family, step.kind, step.config) for step in current]
        carried: list[ChainStep] = []
        for index, step in enumerate(proposed):
            # 1. The same provider at the same endpoint in the current chain (never another kind).
            positional = siblings[index] if index < len(siblings) else None
            match = SecretIdentity.pick(family, step.kind, step.config, positional, siblings)
            omitted = [field for field in sorted(SECRET_FIELDS) if field not in step.config]
            # 2. Inherit the omitted secrets the same-endpoint source actually holds.
            update = {
                field: match.source[field] for field in omitted if cls.__held(match.source, field)
            }
            # 3. Endpoint moved: mark the stored secret for re-entry instead of carrying it.
            reentry = [field for field in omitted if cls.__held(match.moved, field)]
            update.update(dict.fromkeys(reentry, MASK))
            if reentry:
                notices.append(
                    f"step {index} ({step.kind}): {', '.join(reentry)} must be re-entered — its "
                    f"endpoint (base_url) changed, so the stored secret is not carried"
                )
            carried.append(
                step.model_copy(update={"config": {**step.config, **update}}) if update else step
            )
        return carried


__all__ = ["ChainSecretCarry"]
