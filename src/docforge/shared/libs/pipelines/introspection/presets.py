# ====== Code Summary ======
# PipelinePreset — the discoverable metadata of ONE creation preset (a curated stock blob a new
# collection can start from). A preset is NOT a new engine: it is a named, validation-passing default
# topology the facade already knows how to assemble. This model carries only what a schema-driven UI
# (or the MCP) needs to offer the choice — the machine name to post, a human label and a rationale —
# never the blob itself (that is resolved server-side by the facade's ``preset_blob``).

# ====== Third-Party Library Imports ======
from pydantic import BaseModel, Field


class PipelinePreset(BaseModel):
    """
    One creation preset a pipeline facade offers — a curated, validation-passing stock blob.

    Attributes:
        name (str): The machine name posted as the creation ``preset`` / ``search_preset`` selector.
        label (str): The human label a UI renders for the choice.
        description (str): Why this preset exists and when to pick it (the rationale).
        is_default (bool): True for the preset a fresh collection gets when none is selected.
    """

    name: str = Field(description="Machine name posted as the creation preset selector.")
    label: str = Field(description="Human label a UI renders for the choice.")
    description: str = Field(description="Why this preset exists and when to pick it.")
    is_default: bool = Field(
        default=False, description="True for the preset selected when none is given."
    )


__all__ = ["PipelinePreset"]
