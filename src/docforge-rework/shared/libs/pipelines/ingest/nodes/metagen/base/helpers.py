# ====== Code Summary ======
# Static helpers of the metagen family — now just the auto-prompt: the default per-field instruction
# used when the config binds no prompt. It is metagen PROMPT WORDING (generative, scope-aware), so it
# stays here. The schema derivation and strict coercion that used to live alongside it were moved to
# the generic structgen capability (StructGenHelpers) — metagen's node calls back into those.

# ====== Third-Party Library Imports ======
from loggerplusplus import loggerplusplus

# ====== Internal Project Imports ======
from shared_libs.public_models import FieldScope, MetadataFieldSpec


class MetagenHelpers:
    """Static utility helpers for the metagen family (the per-field auto-prompt)."""

    logger = loggerplusplus.bind(identifier="MetagenHelpers")

    def __new__(cls, *args: object, **kwargs: object) -> None:
        raise TypeError("MetagenHelpers is a static-only class and cannot be instantiated.")

    @staticmethod
    def auto_prompt(spec: MetadataFieldSpec, scope: FieldScope) -> str:
        """
        The default per-field instruction when the config binds no prompt.

        A GENERATED field is synthesized, not copied: the instruction asks the model to
        produce the field from the whole {scope} rather than to extract a span of the text
        (extractive wording makes a generated summary/title echo a heading verbatim).

        Args:
            spec (MetadataFieldSpec): The field to generate (name + contract type).
            scope (FieldScope): The generation granularity — document or chunk.

        Returns:
            str: A generative, scope-aware instruction for this field.
        """
        return (
            f"Generate the '{spec.field_name}' ({spec.field_type.value}) for this "
            f"{scope.value}, synthesizing it from the {scope.value}'s content."
        )


__all__ = ["MetagenHelpers"]
