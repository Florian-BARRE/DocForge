# ====== Code Summary ======
# DocLanguageNode — the docmeta/language node: a VISIBLE, per-collection step that owns the
# document's language. It runs AFTER parse (so the IR text exists) and BEFORE the figure/OCR stage
# (so tesseract's lang=auto sees it via FigureItem.language). In 'auto' mode it runs the
# dependency-free LanguageDetector over the IR block text; in 'fixed' mode it forces the configured
# code. The parser mappers no longer detect language — they emit language="" and this node fills it.
# Pure: it never touches the input IR, returning a copy with only DocumentIR.language set.

# ====== Third-Party Library Imports ======
from pydantic import Field

# ====== Internal Project Imports ======
from shared_libs.pipelines.base import ActionNode, NodeInput, NodeOutput
from shared_libs.pipelines.registry import NodeRegistry
from shared_libs.public_models import DocumentIR

# ====== Local Project Imports ======
from .config import DocLanguageConfig
from .detector import LanguageDetector


class DocLanguageConsumes(NodeInput):
    """Input: the parsed IR whose dominant language is to be resolved."""

    ir: DocumentIR = Field(description="The parsed IR whose dominant language is stamped.")


class DocLanguageProduces(NodeOutput):
    """Output: the same IR with DocumentIR.language set."""

    ir: DocumentIR = Field(description="The IR with DocumentIR.language resolved (may be empty).")


@NodeRegistry.register("docmeta")
class DocLanguageNode(ActionNode):
    """Resolve the document's ISO 639-1 language and stamp it onto the IR."""

    KIND = "language"
    NAME = "Language detection"
    SUMMARY = "Resolve the document's ISO 639-1 language and stamp it onto the IR."
    HOW_IT_WORKS = (
        "In 'auto' mode, runs a lightweight, offline stop-word detector over the IR's block text "
        "and normalizes it to an ISO 639-1 code, falling back to 'default_language' when there is "
        "no signal. In 'fixed' mode, forces 'default_language' verbatim. The result is stamped onto "
        "DocumentIR.language, which downstream figure OCR (tesseract lang=auto) and the catalog read."
    )
    Config = DocLanguageConfig
    UNIQUE_IN_GRAPH = True
    Consumes = DocLanguageConsumes
    Produces = DocLanguageProduces

    async def run(self, data: DocLanguageConsumes) -> DocLanguageProduces:
        """
        Resolve the document language and return the IR with it stamped.

        Args:
            data (DocLanguageConsumes): The parsed IR to annotate.

        Returns:
            DocLanguageProduces: A copy of the IR with DocumentIR.language set.
        """
        config: DocLanguageConfig = self.config
        # 1. In fixed mode the configured code wins outright — no detection is run.
        if config.mode == "fixed":
            language = config.default_language
        else:
            # 2. Auto mode: detect over the IR text, falling back to the configured default when the
            #    text carries no distinguishing signal (never a wrong guess).
            text = " ".join(
                block.text for block in data.ir.blocks if block.text and block.text.strip()
            )
            language = LanguageDetector.detect(text) or config.default_language

        # 3. Pure: never mutate the input IR — return a copy carrying only the resolved language.
        self.logger.debug(f"Document '{data.ir.doc_id}' language resolved to {language!r}")
        return DocLanguageProduces(ir=data.ir.model_copy(update={"language": language}))


__all__ = [
    "DocLanguageNode",
    "DocLanguageConfig",
    "DocLanguageConsumes",
    "DocLanguageProduces",
]
