# ====== Code Summary ======
# BaseDoclingParserNode — the shared scaffold behind every Docling-family parser (the standard modular
# pipeline and the Granite VLM pipeline). It owns the parse plumbing common to both: a PROCESS-WIDE,
# per-concrete-class DocumentConverter cache (building one loads native/model weights — tens of
# seconds — so it happens once per option set, not per document), the temp-file write + the convert()
# call, and the map to the canonical IR via the UNCHANGED DoclingIRMapper. The heavy convert runs in a
# KILLABLE subprocess the worker manages (DoclingSubprocessPool), NOT a worker thread: a thread that
# OOMs or hangs mid-convert can never be killed and wedges the worker (and, holding the old convert
# lock, deadlocks every future parse); a subprocess is SIGKILLed on a time/memory cap and respawned,
# so one pathological document becomes a clean, attributed single-job failure. The pure convert body
# (`_convert_to_ir`) is what runs INSIDE that child. Children implement ONLY _build_converter (their
# engine) and _cache_key (its option axes). I/O, scoring and the native/PDF degradation stay in
# BaseParserNode; the subprocess caps live on BaseDoclingParserConfig.

# ====== Standard Library Imports ======
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
from .config import BaseDoclingParserConfig
from .subprocess import DoclingSubprocessPool


class BaseDoclingParserNode(BaseParserNode):
    """Abstract Docling-family parser: shared converter cache + killable-subprocess parse + IR mapping."""

    # A stable discriminator for the pipeline flavour this node runs (e.g. "standard", "vlm"). It is
    # the FIRST element of every cache key so two Docling flavours can never share a cached converter —
    # a belt-and-braces guard on top of each concrete class owning its OWN cache dict (below).
    _PIPELINE: str = "docling"

    # Structured text formats read natively from the ORIGINAL bytes → temp-file suffix (Docling picks
    # its backend from the extension). A child with no native path leaves NATIVE_FORMATS empty and
    # never reaches this lookup.
    _NATIVE_SUFFIX: dict[str, str] = {"html": ".html", "md": ".md"}

    # Process-wide converter CACHE + locks (they live in the PARSE SUBPROCESS, where convert() runs).
    # Declared here so the shared methods type-check; EACH concrete subclass REDEFINES these three so
    # the standard and VLM caches never share a dict/lock.
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

    def _convert_to_ir(self, content: bytes, suffix: str, source_hash: str) -> DocumentIR:
        """Convert the bytes and map to the IR — the PURE parse body that runs in the parse subprocess.

        This is the heavy, native step (docling ``convert()`` + IR mapping). It is invoked by the
        subprocess child, not the worker thread, so an OOM or a native hang here kills the isolated
        child (which the worker respawns) instead of wedging the worker. It stays a plain sync method
        so it is equally callable in-process (tests exercising the docling error-unwrap directly).

        Args:
            content (bytes): The PDF (or native html/md) bytes to convert.
            suffix (str): The temp-file extension Docling picks its backend from.
            source_hash (str): The IR document id / source hash.

        Returns:
            DocumentIR: The mapped canonical IR (no figure crops yet — figure_render embeds those).
        """
        # 1. Resolve the shared converter (built once per option set, cached in THIS process).
        converter = self.__converter()

        # 2. Docling needs a file path and picks its backend from the extension — write the bytes to a
        #    temp file with the format's suffix, convert, always clean up.
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
            tmp.write(content)
            tmp_path = Path(tmp.name)
        try:
            # 3. Serialize conversions — the shared converter is not documented thread-safe (harmless,
            #    uncontended, in the single-threaded child; still correct if called in-process).
            with self._convert_lock:
                result = converter.convert(str(tmp_path))
            return DoclingIRMapper.map_document(
                result.document, doc_id=source_hash, source_hash=source_hash
            )
        except Exception as exc:
            # 3b. Docling collapses the real failure into a generic `RuntimeError("Pipeline X failed")
            #     from <cause>` (base_pipeline.py). Re-raise with that chained cause in the MESSAGE so
            #     job.error / the run breadcrumb name the ACTUAL error (e.g. a GPU torch.compile/CUDA
            #     failure) instead of the opaque wrapper — every docling failure otherwise reads
            #     identically and can't be diagnosed without shell access to prod. `from exc` keeps the
            #     full chained traceback in the child's logs; the message crosses back to the parent.
            cause = exc.__cause__ or exc.__context__
            if cause is not None and cause is not exc:
                raise RuntimeError(f"{exc}: {type(cause).__name__}: {cause}") from exc
            raise
        finally:
            # 4. A leftover temp file is harmless; Windows may still hold the handle briefly.
            try:
                tmp_path.unlink(missing_ok=True)
            except OSError:
                self.logger.warning(f"Could not remove temp file {tmp_path}; leaving it behind")

    async def _parse(self, source: IntakeResult) -> DocumentIR:
        """Run the CPU/GPU-bound Docling conversion in a KILLABLE subprocess and map it to the IR.

        Parses the PDF view when one exists; otherwise the ORIGINAL bytes of a natively-parsed format
        (NATIVE_FORMATS), whose heading tree a PDF round-trip would flatten. Delegates the actual
        convert to the process-wide subprocess pool, bounded by the node's per-collection time/memory
        caps — a document too heavy for docling fails cleanly (attributed) without ever wedging the
        worker.
        """
        if source.pdf_content is not None:
            content, suffix = source.pdf_content, ".pdf"
        else:
            content = source.source_content or b""
            suffix = self._NATIVE_SUFFIX[source.source_format]
        config: BaseDoclingParserConfig = self.config
        return await DoclingSubprocessPool.instance().parse(
            node_class=type(self),
            config=self.config,
            content=content,
            suffix=suffix,
            source_hash=source.source_hash,
            timeout_seconds=config.parse_timeout_seconds,
            memory_mb=config.parse_memory_mb,
        )


__all__ = ["BaseDoclingParserNode"]
