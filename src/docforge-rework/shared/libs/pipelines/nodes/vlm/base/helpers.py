# ====== Code Summary ======
# BaseVlmHelpers — pure post-processing of a VLM response: extracting the fenced ```table``` block
# (the chart-to-table output) into rows and stripping it from the description. Cells split on
# pipes (markdown-style) with a comma fallback. No I/O, no side effects.

# ====== Standard Library Imports ======
import re

# The fenced block the chart-to-table instruction asks for.
_TABLE_BLOCK = re.compile(r"```table\s*\n(.*?)```", re.DOTALL | re.IGNORECASE)


class BaseVlmHelpers:
    """Static response post-processing for the VLM family."""

    def __new__(cls, *args: object, **kwargs: object) -> None:
        raise TypeError("BaseVlmHelpers is a static-only class and cannot be instantiated.")

    @staticmethod
    def __split_row(line: str) -> list[str]:
        """Split one table line into cells — pipes first (markdown), comma fallback."""
        if "|" in line:
            return [cell.strip() for cell in line.strip().strip("|").split("|")]
        return [cell.strip() for cell in line.split(",")]

    @classmethod
    def extract_table(cls, response: str) -> tuple[str, list[list[str]] | None]:
        """
        Pull the fenced ```table``` block out of a response.

        Args:
            response (str): The raw VLM answer.

        Returns:
            tuple[str, list | None]: (the description without the block, the parsed rows or None).
        """
        match = _TABLE_BLOCK.search(response)
        if match is None:
            return response.strip(), None
        # 1. Parse the block's non-empty lines into rows (markdown separator lines dropped).
        rows = [
            cls.__split_row(line)
            for line in match.group(1).splitlines()
            if line.strip() and not set(line.strip()) <= {"|", "-", " ", ":"}
        ]
        # 2. The description is the response without the block.
        description = _TABLE_BLOCK.sub("", response).strip()
        return description, rows or None


__all__ = ["BaseVlmHelpers"]
