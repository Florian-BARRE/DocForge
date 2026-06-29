# ====== Code Summary ======
# ParseResult dataclass — the canonical output contract of the parse stage (relocated from the
# former parse result type, with byte-identical fields so the node-cache codec round-trip stays
# unchanged). It is the artefact every downstream consumer reads (enrich, the worker node-cache
# codec, the persist/trace layer): the canonical IR (with the parse ChainTrace stamped), the
# markdown view's object-store key, and the per-figure crop keys. Kept in its own module so it can
# be imported without pulling in the stage's parser-chain / object-store dependencies.

# ====== Standard Library Imports ======
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from common_libs.domain.ir.models import DocumentIR


@dataclass(slots=True)
class ParseResult:
    """
    Output artefacts produced by the parse stage.

    Attributes:
        ir (DocumentIR): The canonical IR, with the parse ChainTrace appended.
        markdown_key (str | None): Object-store key for the faithful markdown view.
            ``None`` only in the degraded no-parse case (parse gate failure_policy=continue,
            chain exhausted) — there is no IR to serialise so no markdown is uploaded.
        figure_crop_keys (dict[str, str]): block_id → object-store key for each figure crop.
    """

    ir: "DocumentIR"
    markdown_key: str | None
    figure_crop_keys: dict[str, str]


__all__ = ["ParseResult"]
