# ====== Code Summary ======
# RapidOcrEngine — the ONE process-shared local RapidOCR runner (onnxruntime CPU, models bundled).
# Extracted from the OCR node so it can be reused as a pure LOCAL signal by more than the OCR family:
# the local figure classifier reads the same engine to measure a crop's text density. It lazy-imports
# the native dependency, shares ONE engine process-wide (built once), serialises the non-reentrant
# inference and runs the CPU-bound reading off the event loop. It returns the RAW readings so each
# caller derives exactly what it needs (joined text + mean confidence for the OCR node, box coverage
# for the classifier) — the engine itself does zero interpretation and no DB/S3 I/O.

# ====== Standard Library Imports ======
import asyncio
import threading
from typing import Any

# ====== Third-Party Library Imports ======
from loggerplusplus import loggerplusplus


class RapidOcrEngine:
    """Static access to the process-shared RapidOCR engine (lazy native import, serialised reads)."""

    logger = loggerplusplus.bind(identifier="RapidOcrEngine")

    # ONE engine per process — model load happens once, every caller reuses it.
    _engine: Any = None
    _engine_lock = threading.Lock()
    # The RapidOCR wrapper holds mutable pre/post state, so its inference is NOT re-entrant across
    # threads. Concurrent jobs, the per-figure enrich ForEach and the local classifier all fan reads
    # onto to_thread workers that share this one engine — serialise the sync call to avoid latent
    # state corruption. The lock lives inside the worker thread only, so the event loop is never
    # blocked.
    _inference_lock = threading.Lock()

    def __new__(cls, *args: object, **kwargs: object) -> None:
        raise TypeError("RapidOcrEngine is a static-only class and cannot be instantiated.")

    @classmethod
    def __resolve(cls) -> Any:
        """Build the process-shared RapidOCR engine on first use (lazy native import)."""
        with cls._engine_lock:
            if cls._engine is None:
                from rapidocr_onnxruntime import RapidOCR

                cls._engine = RapidOCR()
        return cls._engine

    @classmethod
    def __run_sync(cls, image: bytes) -> list:
        """Synchronous OCR (runs in a worker thread) → the raw readings list (or empty)."""
        engine = cls.__resolve()
        # RapidOCR returns (list of [box, text, confidence] | None, elapse_times). Serialise the
        # call: the shared engine's mutable pre/post state is not thread-safe under concurrent reads.
        with cls._inference_lock:
            readings, _elapsed = engine(image)
        return list(readings) if readings else []

    @classmethod
    async def read(cls, image: bytes) -> list:
        """
        Run the local OCR off the event loop and return the raw readings.

        Args:
            image (bytes): The crop to read.

        Returns:
            list: The RapidOCR readings — one ``[box, text, confidence]`` entry per detected line
            (empty when nothing was read).
        """
        return await asyncio.to_thread(cls.__run_sync, image)

    @staticmethod
    def to_text(readings: list) -> tuple[str, float]:
        """
        Fold raw readings into the OCR node's contract: newline-joined text + mean confidence.

        Args:
            readings (list): The raw RapidOCR readings.

        Returns:
            tuple[str, float]: The joined text and the mean per-line confidence (0.0 when empty).
        """
        # 1. No line detected — an empty, zero-confidence reading (a ScoreBelow escalates on it).
        if not readings:
            return "", 0.0
        # 2. Each entry is [box, text, confidence]; join the lines and average the confidences.
        lines = [entry[1] for entry in readings]
        confidences = [float(entry[2]) for entry in readings]
        return "\n".join(lines), sum(confidences) / len(confidences)


__all__ = ["RapidOcrEngine"]
