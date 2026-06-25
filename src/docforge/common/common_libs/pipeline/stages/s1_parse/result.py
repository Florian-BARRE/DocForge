# ====== Code Summary ======
# S1Result dataclass — output artefacts produced by the S1 parsing stage.
# Extracted from s1_parse.py to keep the result model separately importable
# without pulling in all of S1ParseStage's dependencies.

# ====== Standard Library Imports ======
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from common_libs.domain.ir.models import DocumentIR


@dataclass(slots=True)
class S1Result:
    """
    Output artefacts produced by the S1 parsing stage.

    Attributes:
        ir (DocumentIR): The canonical IR, with the parse ChainTrace appended.
        markdown_key (str | None): Object-store key for the faithful markdown view.
            ``None`` only in the degraded no-parse case (parse gate failure_policy=continue,
            chain exhausted) — there is no IR to serialise so no markdown is uploaded.
        figure_crop_keys (dict[str, str]): block_id → object-store key for each figure crop.
    """

    ir: DocumentIR
    markdown_key: str | None
    figure_crop_keys: dict[str, str]
