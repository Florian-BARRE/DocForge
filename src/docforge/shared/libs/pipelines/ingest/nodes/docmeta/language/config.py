# ====== Code Summary ======
# The config of the docmeta/language node — how the document language is decided: detected from the
# IR text (``auto``) or forced to a fixed code (``fixed``). ``default_language`` is the ISO 639-1
# code used when ``fixed``, OR the fallback when ``auto`` finds no signal (empty keeps "").

# ====== Standard Library Imports ======
from typing import Literal

# ====== Third-Party Library Imports ======
from pydantic import Field

# ====== Internal Project Imports ======
from shared_libs.pipelines.base import NodeConfig


class DocLanguageConfig(NodeConfig):
    """Knobs deciding the document's ISO 639-1 language stamped onto the IR."""

    mode: Literal["auto", "fixed"] = Field(
        default="auto",
        description=(
            "How the language is decided: 'auto' runs the stop-word detector over the IR text; "
            "'fixed' forces 'default_language' regardless of the text."
        ),
    )
    default_language: str = Field(
        default="",
        description=(
            "The ISO 639-1 code applied when mode='fixed', OR the fallback when mode='auto' finds "
            "no signal (empty keeps the language unset)."
        ),
    )


__all__ = ["DocLanguageConfig"]
