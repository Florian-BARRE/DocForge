# ====== Code Summary ======
# IO contract for the markdown step: it consumes the patched IR + the figure crop keys (figure-render)
# and the degraded flag (parse), plus the source hash from the parent stage input (to key the markdown
# blob), and produces the durable ParseResult plus the final IR — the parse stage's output contract.

# ====== Standard Library Imports ======
from typing import Annotated

# ====== Internal Project Imports ======
from common_libs.domain.ir.models import DocumentIR
from common_libs.pipelines import FromParent, FromSibling, NodeInput, NodeOutput

# ====== Local Project Imports ======
from ...result import ParseResult


class IngestStageParseStepMarkdownInput(NodeInput):
    """
    Input of the markdown step.

    Attributes:
        ir (DocumentIR): The patched IR (from the figure-render step).
        figure_crop_keys (dict[str, str]): block_id -> crop key (from the figure-render step).
        degraded (bool): The degraded flag (from the parse step) — skip serialisation when True.
        source_hash (str): The original content address (from the stage input) — keys the md blob.
    """

    ir: Annotated[DocumentIR, FromSibling(producer="figure_render", field="ir")]
    figure_crop_keys: Annotated[
        dict[str, str], FromSibling(producer="figure_render", field="figure_crop_keys")
    ]
    degraded: Annotated[bool, FromSibling(producer="parse", field="degraded")]
    source_hash: Annotated[str, FromParent(field="source_hash")]


class IngestStageParseStepMarkdownOutput(NodeOutput):
    """
    Output of the markdown step.

    Attributes:
        parse_result (ParseResult): The durable artefact (IR + markdown key + figure crop keys).
        ir (DocumentIR): The final canonical IR (passed through unchanged).
    """

    parse_result: ParseResult
    ir: DocumentIR


__all__ = ["IngestStageParseStepMarkdownInput", "IngestStageParseStepMarkdownOutput"]
