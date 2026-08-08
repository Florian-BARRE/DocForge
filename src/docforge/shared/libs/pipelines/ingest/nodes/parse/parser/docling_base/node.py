# ====== Code Summary ======
# BaseDoclingParserNode — the shared scaffold behind every Docling-family parser (the standard
# modular pipeline and the Granite VLM pipeline). It owns the parse plumbing common to both: a
# PROCESS-WIDE, per-concrete-class DocumentConverter cache (building one loads native/model weights —
# tens of seconds — so it happens once per option set, not per document), the temp-file write + the
# CPU-bound convert() run in a worker thread under a lock (convert() is not documented thread-safe),
# and the map to the canonical IR via the UNCHANGED DoclingIRMapper. Children implement ONLY
# _build_converter (their engine) and _cache_key (its option axes). I/O, scoring and the native/PDF
# degradation stay in BaseParserNode.

# ====== Standard Library Imports ======
import asyncio
import tempfile
import threading
from abc import abstractmethod
from pathlib import Path
from typing import Any

# ====== Internal Project Imports ======
from shared_libs.public_models import DocumentIR, IntakeResult

# ====== Local Project Imports ======
from ..base import BaseParserNode
from ..docling.mapper import DoclingIRMapper


class BaseDoclingParserNode(BaseParserNode):
    """Abstract Docling-family parser: shared converter cache + parse plumbing + IR mapping."""

    # A stable discriminator for the pipeline flavour this node runs (e.g. "standard", "vlm"). It is
    # the FIRST element of every cache key so two Docling flavours can never share a cached converter —
    # a belt-and-braces guard on top of each concrete class owning its OWN cache dict (below).
    _PIPELINE: str = "docling"

    # Structured text formats read natively from the ORIGINAL bytes → temp-file suffix (Docling picks
    # its backend from the extension). A child with no native path leaves NATIVE_FORMATS empty and
    # never reaches this lookup.
    _NATIVE_SUFFIX: dict[str, str] = {"html": ".html", "md": ".md"}

    # Process-wide converter CACHE + locks. Declared here so the shared methods type-check; EACH
    # concrete subclass REDEFINES these three so the standard and VLM caches never share a dict/lock.
    _converters: dict[tuple[Any, ...], Any] = {}
    _build_lock: threading.Lock = threading.Lock()
    _convert_lock: threading.Lock = threading.Lock()

    @abstractmethod
    def _build_converter(self) -> Any:
        """Build the engine-specific Docling DocumentConverter (called once per cache key)."""
        ...

    @abstractmethod
    def _cache_key(self) -> tuple[Any, ...]:
        """The option axes that identify this node's converter within its class-local cache."""
        ...

    def __converter(self) -> Any:
        """Resolve the process-shared DocumentConverter for this node's options (build once)."""
        # 1. Prefix the pipeline discriminator so no two flavours' keys can ever collide.
        key = (self._PIPELINE, *self._cache_key())
        # 2. Build the converter once per key (double-checked under the build lock).
        with self._build_lock:
            if key not in self._converters:
                self._converters[key] = self._build_converter()
                self.logger.info(f"Docling converter built for {key}")
        return self._converters[key]

    def __parse_sync(self, content: bytes, suffix: str, source_hash: str) -> DocumentIR:
        """Synchronous Docling parse (runs in a worker thread): convert the bytes, map to the IR."""
        # 1. Resolve the shared converter (built once per option set).
        converter = self.__converter()

        # 2. Docling needs a file path and picks its backend from the extension — write the bytes to
        #    a temp file with the format's suffix, convert, always clean up.
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
            tmp.write(content)
            tmp_path = Path(tmp.name)
        try:
            # 3. Serialize conversions — the shared converter is not documented thread-safe.
            with self._convert_lock:
                result = converter.convert(str(tmp_path))
            return DoclingIRMapper.map_document(
                result.document, doc_id=source_hash, source_hash=source_hash
            )
        finally:
            # 4. A leftover temp file is harmless; Windows may still hold the handle briefly.
            try:
                tmp_path.unlink(missing_ok=True)
            except OSError:
                self.logger.warning(f"Could not remove temp file {tmp_path}; leaving it behind")

    async def _parse(self, source: IntakeResult) -> DocumentIR:
        """Run the CPU-bound Docling conversion off the event loop and map it to the IR.

        Parses the PDF view when one exists; otherwise the ORIGINAL bytes of a natively-parsed format
        (NATIVE_FORMATS), whose heading tree a PDF round-trip would flatten.
        """
        if source.pdf_content is not None:
            content, suffix = source.pdf_content, ".pdf"
        else:
            content = source.source_content or b""
            suffix = self._NATIVE_SUFFIX[source.source_format]
        return await asyncio.to_thread(self.__parse_sync, content, suffix, source.source_hash)


__all__ = ["BaseDoclingParserNode"]
