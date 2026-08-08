# ====== Code Summary ======
# The semantic chunker — embedding-window splitting: the passages are cut into sentence units,
# each unit's CONTEXT WINDOW (the unit ± buffer neighbours) is embedded, and a chunk boundary is
# placed wherever the cosine distance between consecutive windows jumps above the configured
# percentile — i.e. where the TOPIC shifts. Size bounds then merge the too-small and cut the
# too-large groups. Needs an OpenAI-compatible embeddings endpoint (bge_server, OpenAI, …).

# ====== Third-Party Library Imports ======
from pydantic import Field

# ====== Internal Project Imports ======
from shared_libs.pipelines.nodes.openai_compat import OpenAICompatConfig, OpenAICompatHelpers
from shared_libs.pipelines.registry import NodeRegistry

# ====== Local Project Imports ======
from ..base import BaseChunkerConfig, BaseChunkerNode, Passage
from .helpers import SemanticChunkerHelpers


class ChunkerSemanticConfig(BaseChunkerConfig, OpenAICompatConfig):
    """Semantic knobs — the boundary detector (endpoint fields inherited)."""

    model: str = Field(description="Embedding model name (e.g. BAAI/bge-m3).")
    buffer_size: int = Field(
        default=1, ge=0, description="Neighbour sentences on each side of a unit's context window."
    )
    breakpoint_percentile: float = Field(
        default=90.0,
        ge=0.0,
        le=100.0,
        description="Distance percentile above which a boundary is placed (higher = fewer cuts).",
    )
    min_tokens: int = Field(
        default=64, ge=0, description="Groups below this merge with a neighbour."
    )
    max_tokens: int = Field(default=1024, gt=0, description="Hard cap; larger groups are re-cut.")


@NodeRegistry.register("chunker")
class ChunkerSemanticNode(BaseChunkerNode):
    """Cut where the topic shifts — embedding-window boundary detection."""

    KIND = "semantic"
    NAME = "Semantic"
    SUMMARY = "Chunk at topic shifts, detected by embedding-window distance jumps."
    HOW_IT_WORKS = (
        "Splits the text into sentence units, embeds each unit's context window (± buffer "
        "neighbours), and places a boundary wherever the cosine distance between consecutive "
        "windows exceeds the configured percentile. Size bounds then merge or re-cut the groups."
    )
    Config = ChunkerSemanticConfig
    UNIQUE_IN_GRAPH = True

    async def _embed(self, texts: list[str]) -> list[list[float]]:
        """Embed the context windows through the configured endpoint (overridable hook)."""
        config: ChunkerSemanticConfig = self.config
        return await OpenAICompatHelpers.embeddings(
            config, max_retries=config.max_retries
        ).aembed_documents(texts)

    def __boundaries(self, distances: list[float]) -> set[int]:
        """The unit indexes AFTER which a boundary is placed."""
        config: ChunkerSemanticConfig = self.config
        threshold = SemanticChunkerHelpers.percentile(distances, config.breakpoint_percentile)
        return {index for index, distance in enumerate(distances) if distance > threshold}

    def __apply_size_bounds(self, groups: list[list[Passage]]) -> list[list[Passage]]:
        """Merge too-small groups into their predecessor; re-cut groups above the hard cap."""
        config: ChunkerSemanticConfig = self.config
        # 1. Merge the too-small into the previous group (topic-adjacent by construction).
        merged: list[list[Passage]] = []
        for group in groups:
            tokens = sum(passage.token_count for passage in group)
            if merged and tokens < config.min_tokens:
                merged[-1].extend(group)
                continue
            merged.append(group)
        # 2. Re-cut anything above the hard cap at unit boundaries.
        bounded: list[list[Passage]] = []
        for group in merged:
            current: list[Passage] = []
            current_tokens = 0
            for passage in group:
                if current and current_tokens + passage.token_count > config.max_tokens:
                    bounded.append(current)
                    current, current_tokens = [], 0
                current.append(passage)
                current_tokens += passage.token_count
            if current:
                bounded.append(current)
        return bounded

    async def _split(self, passages: list[Passage]) -> list[list[Passage]]:
        """Sentence units → embedded context windows → boundaries at distance jumps → bounds."""
        config: ChunkerSemanticConfig = self.config
        # 1. Sentence units — explode(0) cuts every non-atomic passage down to sentences; the
        #    second explode hard-cuts any boundary-less unit still above the hard cap (atomic
        #    passages pass through both, whole).
        units = [
            unit
            for passage in passages
            for sentence in passage.explode(0, config.tokenizer_encoding)
            for unit in sentence.explode(config.max_tokens, config.tokenizer_encoding)
        ]
        if len(units) <= 2:
            return [units] if units else []

        # 2. Embed each unit's context window (the unit ± buffer neighbours).
        windows = [
            " ".join(
                unit.text
                for unit in units[
                    max(0, index - config.buffer_size) : index + config.buffer_size + 1
                ]
            )
            for index in range(len(units))
        ]
        vectors = await self._embed(windows)

        # 3. Boundaries where the distance between consecutive windows jumps.
        distances = [
            SemanticChunkerHelpers.cosine_distance(vectors[index], vectors[index + 1])
            for index in range(len(vectors) - 1)
        ]
        boundaries = self.__boundaries(distances)

        # 4. Group the units, then enforce the size bounds.
        groups: list[list[Passage]] = [[]]
        for index, unit in enumerate(units):
            groups[-1].append(unit)
            if index in boundaries:
                groups.append([])
        return self.__apply_size_bounds([group for group in groups if group])


__all__ = ["ChunkerSemanticNode", "ChunkerSemanticConfig"]
