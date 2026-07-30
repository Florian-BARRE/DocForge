# ====== Code Summary ======
# Static math helpers of the semantic chunker: cosine distance between embedding vectors and the
# percentile threshold over the distance series. Hand-rolled on purpose — the shared socle does
# not depend on numpy for two ten-line formulas.

# ====== Standard Library Imports ======
import math


class SemanticChunkerHelpers:
    """Static utility helpers for ChunkerSemanticNode."""

    def __new__(cls, *args: object, **kwargs: object) -> None:
        raise TypeError("SemanticChunkerHelpers is a static-only class and cannot be instantiated.")

    @staticmethod
    def cosine_distance(left: list[float], right: list[float]) -> float:
        """
        1 - cosine similarity between two vectors (0 = identical direction, 2 = opposite).

        Args:
            left (list[float]): First embedding.
            right (list[float]): Second embedding.

        Returns:
            float: The cosine distance; 1.0 when either vector is null.
        """
        # 1. A null vector has no direction — treat it as maximally uninformative.
        dot = sum(a * b for a, b in zip(left, right, strict=True))
        norm_left = math.sqrt(sum(a * a for a in left))
        norm_right = math.sqrt(sum(b * b for b in right))
        if norm_left == 0.0 or norm_right == 0.0:
            return 1.0
        return 1.0 - dot / (norm_left * norm_right)

    @staticmethod
    def percentile(values: list[float], rank: float) -> float:
        """
        The value at the given percentile (linear interpolation between closest ranks).

        Args:
            values (list[float]): The series (non-empty).
            rank (float): Percentile in [0, 100].

        Returns:
            float: The interpolated percentile value.
        """
        # 1. Interpolate between the two ranks surrounding the requested one.
        ordered = sorted(values)
        position = (len(ordered) - 1) * rank / 100.0
        lower = int(position)
        upper = min(lower + 1, len(ordered) - 1)
        fraction = position - lower
        return ordered[lower] * (1.0 - fraction) + ordered[upper] * fraction


__all__ = ["SemanticChunkerHelpers"]
