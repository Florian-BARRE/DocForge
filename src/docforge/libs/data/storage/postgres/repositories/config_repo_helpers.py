# ====== Code Summary ======
# Static, stateless helpers for ConfigRepository: pipeline-version increment and
# metadata-field ORM construction. Extracted to keep ConfigRepository focused on
# session-bound data-access operations.

# ====== Standard Library Imports ======
import re
from typing import Any

# ====== Third-Party Library Imports ======
from loggerplusplus import loggerplusplus

# ====== Local Project Imports ======
from ..models import MetadataFieldModel


class ConfigRepoHelpers:
    """
    Pure, stateless helpers for ConfigRepository.

    Contains utilities that depend neither on a database session nor on instance
    state: pipeline-version tag incrementing and building a MetadataFieldModel
    from a normalized field spec.
    """

    logger = loggerplusplus.bind(identifier="ConfigRepoHelpers")

    def __new__(cls, *args: object, **kwargs: object) -> None:
        """Block instantiation — this is a static-only helper class."""
        raise TypeError("ConfigRepoHelpers is a static-only class and cannot be instantiated.")

    @staticmethod
    def next_pipeline_version(current: str) -> str:
        """
        Increment the trailing integer of a pipeline_version tag (``v1`` → ``v2``).

        Falls back to appending ``-2`` when no trailing integer is present.

        Args:
            current (str): The current pipeline_version tag.

        Returns:
            str: The incremented pipeline_version tag.
        """
        match = re.search(r"(\d+)$", current or "")
        if match:
            return f"{current[: match.start()]}{int(match.group(1)) + 1}"
        return f"{current or 'v1'}-2"

    @staticmethod
    def build_field(spec: dict[str, Any]) -> MetadataFieldModel:
        """
        Build a MetadataFieldModel from a normalized metadata-field dict (no collection_id).

        Args:
            spec (dict[str, Any]): Normalized metadata-field specification.

        Returns:
            MetadataFieldModel: The unattached ORM instance.
        """
        return MetadataFieldModel(
            field_name=spec["field_name"],
            field_type=spec.get("field_type", "string"),
            required=bool(spec.get("required", False)),
            filterable=bool(spec.get("filterable", False)),
            lexical=bool(spec.get("lexical", False)),
            semantic=bool(spec.get("semantic", False)),
            enum_values=spec.get("enum_values"),
            is_system=bool(spec.get("is_system", False)),
        )
