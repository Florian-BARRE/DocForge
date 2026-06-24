# ====== Code Summary ======
# Discriminated-union type aliases, the backward-compat ProviderSpec model, and
# shared constants (SPLIT_METHODS, DEFAULT_HEADING_RULES) used across all
# stage config modules.
#
# Type aliases are intentionally typed as Any — the leaf constraint forbids
# importing concrete provider classes at module level.  At runtime, Pydantic
# validates each list item via the discriminator="id" on the concrete models;
# the unions are built dynamically by build_union(get_configs("category")).
#
# LEAF CONSTRAINT: no module-level import of libs.providers / libs.data /
# libs.pipeline / libs.config.

# ====== Standard Library Imports ======
from __future__ import annotations

from typing import Any

# ====== Third-Party Library Imports ======
from pydantic import BaseModel, Field

# ====== Discriminated Union Type Aliases ======
# Typed as Any so this module remains a leaf (no capability imports at module level).

ParserConfig = Any
ClassifierConfig = Any
OcrProviderConfig = Any
VlmProviderConfig = Any
EmbedProviderConfig = Any

# SplitMethodConfig: Any for the same leaf-constraint reason.
SplitMethodConfig = Any


# ====== Backward-compat ProviderSpec (kept for other modules that import it) ======

class ProviderSpec(BaseModel):
    """
    A single provider selection with its own configuration parameters.

    Kept for backward compatibility — internal code should migrate to typed union configs.

    Attributes:
        id (str): Provider identifier (e.g. "mistral_ocr", "paddle_ocr", "openai_compat").
        params (dict): Free-form provider params — credentials (api_key), endpoints
            (base_url), model ids, device flags.  Missing params fall back to deployment
            defaults in the registry.  This is what lets the UI supply a key on the fly.
    """

    id: str
    params: dict[str, Any] = Field(default_factory=dict)


# ====== Shared Constants ======

# Intra-section split methods understood by S4 (the "decision tree" discriminator).
# Each method reads its own keys from its typed config (see params.py + SplitMethodConfig).
SPLIT_METHODS: frozenset[str] = frozenset({"token_budget", "semantic", "sentence_window"})

# Sensible default heading rules for FR/EN administrative + technical documents.
# Ordered by priority — the first matching pattern sets the heading level. Used to recover
# structure the parser flattened (numbered sections, ARTICLE/ANNEXE/PARTIE, bold titles).
DEFAULT_HEADING_RULES: list[dict[str, Any]] = [
    {"level": 1, "pattern": r"^\s*(PARTIE|TITRE|LIVRE|PART)\s+[IVXLC0-9]"},
    {"level": 1, "pattern": r"^\s*(ANNEXE|ANNEX|APPENDIX)\s+[A-Z0-9]"},
    {"level": 2, "pattern": r"^\s*(CHAPITRE|CHAPTER)\s+[IVXLC0-9]"},
    {"level": 2, "pattern": r"^\s*(ARTICLE|ART\.)\s+\d+"},
    {"level": 2, "pattern": r"^\*\*[A-ZÉÀÈÊÎÔÙÛÜÆŒ][^*]{2,}\*\*\s*$"},
    {"level": 3, "pattern": r"^\s*(SECTION|Section)\s+[\d.]+"},
    {"level": 3, "pattern": r"^\s*\d+\.\s+[A-ZÉÀÈÊÎÔÙÛÜÆŒ]"},
    {"level": 4, "pattern": r"^\s*\d+\.\d+\.?\s+\S"},
    {"level": 5, "pattern": r"^\s*\d+\.\d+\.\d+\.?\s+\S"},
]
