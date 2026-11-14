# ====== Code Summary ======
# BgeEmbedEncoder: the encode paths over the loaded BGEM3FlagModel -- dense, sparse, combined
# dense+sparse (ONE forward pass) and ColBERT multi-vector. Each method requests only the heads it
# needs from ``embed_model.encode``, times the model call, and post-processes the output into the
# JSON-serialisable shapes of the HTTP contract (TEI-shaped sparse token lists, plain Python lists).
# The model and the device label are read through injected getters so the encoder always sees the
# service's CURRENT state (None before load(), the loaded instance after, whatever a test injects).

# ====== Standard Library Imports ======
import time
from collections.abc import Callable
from typing import Any

# ====== Third-Party Library Imports ======
from loggerplusplus import LoggerClass


class BgeEmbedEncoder(LoggerClass):
    """Runs the BGE-M3 encode heads on the shared embed_model and shapes their outputs."""

    def __init__(
        self,
        embed_model: Callable[[], Any],
        device: Callable[[], str | None],
    ) -> None:
        """
        Args:
            embed_model (Callable): Returns the loaded BGEM3FlagModel (raises RuntimeError when
                the service has not been loaded yet).
            device (Callable): Returns the resolved device string, or None before load().
        """
        LoggerClass.__init__(self)
        self._embed_model = embed_model
        self._device = device

    def encode_dense(self, texts: list[str], max_length: int) -> list[list[float]]:
        """
        Encode a batch of texts into dense L2-normalized vectors.

        Args:
            texts (list[str]): Texts to embed. Must be non-empty.
            max_length (int): Maximum token length for truncation.

        Returns:
            list[list[float]]: One 1024-dim float vector per input text.
        """
        device = self._device() or "unknown"
        n = len(texts)
        self.logger.debug(f"encode_dense: {n} texts, max_length={max_length}, device={device}")

        # 1. Run encode requesting only the dense head; time the model call itself
        t0 = time.perf_counter()
        out = self._embed_model().encode(
            texts,
            return_dense=True,
            return_sparse=False,
            return_colbert_vecs=False,
            max_length=max_length,
        )
        elapsed = time.perf_counter() - t0

        # 2. Convert numpy arrays to plain Python lists (JSON-serialisable)
        result = [vec.tolist() for vec in out["dense_vecs"]]
        self.logger.debug(
            f"encode_dense: {n} texts -> {len(result)} vecs in {elapsed:.3f}s (device={device})"
        )
        return result

    def encode_sparse(
        self, texts: list[str], max_length: int
    ) -> list[list[dict[str, int | float]]]:
        """
        Encode a batch of texts into TEI-shaped sparse (lexical) token vectors.

        BGE-M3 returns a ``{token_id(str): weight(float)}`` dict per text; this method
        re-shapes to the TEI contract ``[{"index": int, "value": float}, ...]`` so the
        DocForge ``tei`` provider parses it without modification.

        Args:
            texts (list[str]): Texts to embed. Must be non-empty.
            max_length (int): Maximum token length for truncation.

        Returns:
            list[list[dict]]: Per text, a list of ``{"index": token_id, "value": weight}`` dicts.
        """
        device = self._device() or "unknown"
        n = len(texts)
        self.logger.debug(f"encode_sparse: {n} texts, max_length={max_length}, device={device}")

        # 1. Run encode requesting only the sparse head; time the model call itself
        t0 = time.perf_counter()
        out = self._embed_model().encode(
            texts,
            return_dense=False,
            return_sparse=True,
            return_colbert_vecs=False,
            max_length=max_length,
        )
        elapsed = time.perf_counter() - t0

        # 2. Re-shape from BGE-M3 internal dict to TEI index/value token list
        result: list[list[dict[str, int | float]]] = []
        for weights in out["lexical_weights"]:
            result.append([{"index": int(tok), "value": float(w)} for tok, w in weights.items()])

        self.logger.debug(
            f"encode_sparse: {n} texts -> {len(result)} token-lists in {elapsed:.3f}s (device={device})"
        )
        return result

    def encode_dense_sparse(
        self, texts: list[str], max_length: int
    ) -> tuple[list[list[float]], list[list[dict[str, int | float]]]]:
        """
        Encode a batch of texts into BOTH dense and sparse vectors in ONE forward pass.

        ``encode_dense`` and ``encode_sparse`` each run a full BGE-M3 forward pass; a caller
        that needs both therefore pays two passes of the ~568M model. Requesting both heads from
        a single ``encode(return_dense=True, return_sparse=True)`` call halves that cost. The
        dense and sparse outputs are post-processed with the EXACT same conversions applied by
        ``encode_dense`` and ``encode_sparse``, so the returned shapes are byte-for-byte identical
        to calling those two methods separately.

        Args:
            texts (list[str]): Texts to embed. Must be non-empty.
            max_length (int): Maximum token length for truncation.

        Returns:
            tuple[list[list[float]], list[list[dict]]]: A ``(dense, sparse)`` pair where
                ``dense`` is one 1024-dim float vector per input text (identical to
                ``encode_dense``) and ``sparse`` is, per text, a list of
                ``{"index": token_id, "value": weight}`` dicts (identical to ``encode_sparse``).
        """
        device = self._device() or "unknown"
        n = len(texts)
        self.logger.debug(
            f"encode_dense_sparse: {n} texts, max_length={max_length}, device={device}"
        )

        # 1. One forward pass yielding both the dense and sparse heads; time the model call itself
        t0 = time.perf_counter()
        out = self._embed_model().encode(
            texts,
            return_dense=True,
            return_sparse=True,
            return_colbert_vecs=False,
            max_length=max_length,
        )
        elapsed = time.perf_counter() - t0

        # 2. Dense conversion — mirrors encode_dense (numpy arrays -> plain Python lists)
        dense: list[list[float]] = [vec.tolist() for vec in out["dense_vecs"]]

        # 3. Sparse conversion — mirrors encode_sparse (BGE-M3 dict -> TEI index/value token list)
        sparse: list[list[dict[str, int | float]]] = []
        for weights in out["lexical_weights"]:
            sparse.append([{"index": int(tok), "value": float(w)} for tok, w in weights.items()])

        self.logger.debug(
            f"encode_dense_sparse: {n} texts -> {len(dense)} vecs + {len(sparse)} token-lists "
            f"in {elapsed:.3f}s (device={device})"
        )
        return dense, sparse

    def encode_colbert(self, texts: list[str], max_length: int) -> list[list[list[float]]]:
        """
        Encode a batch of texts into BGE-M3's native ColBERT multi-vector representation.

        Not part of the TEI contract — an internal DocForge convention. Reuses the same
        loaded ``embed_model`` instance as ``encode_dense``/``encode_sparse`` (one shared
        forward pass internally computes dense/sparse/colbert heads together; requesting
        colbert alone here still costs its own forward pass since this call only asks for
        the colbert head).

        Args:
            texts (list[str]): Texts to embed. Must be non-empty.
            max_length (int): Maximum token length for truncation.

        Returns:
            list[list[list[float]]]: Per input text, a list of per-token 1024-dim
                L2-normalized float vectors. Token count varies per text
                (= attention_mask.sum() - 1, i.e. real tokens minus the CLS row).
        """
        device = self._device() or "unknown"
        n = len(texts)
        self.logger.debug(f"encode_colbert: {n} texts, max_length={max_length}, device={device}")

        # 1. Run encode requesting only the colbert head; time the model call itself
        t0 = time.perf_counter()
        out = self._embed_model().encode(
            texts,
            return_dense=False,
            return_sparse=False,
            return_colbert_vecs=True,
            max_length=max_length,
        )
        elapsed = time.perf_counter() - t0

        # 2. Convert per-text numpy arrays ([n_tokens x 1024]) to nested Python lists
        result = [vecs.tolist() for vecs in out["colbert_vecs"]]
        self.logger.debug(
            f"encode_colbert: {n} texts -> {len(result)} token-vector-lists in {elapsed:.3f}s "
            f"(device={device})"
        )
        return result
