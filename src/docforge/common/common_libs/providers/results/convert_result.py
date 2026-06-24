# ====== Code Summary ======
# ConvertResult Pydantic model returned by ConverterProvider implementations.
# Carries the converted PDF bytes and page count back to the stage engine.

# ====== Standard Library Imports ======
# (none)

# ====== Third-Party Library Imports ======
from pydantic import BaseModel

# ====== Internal Project Imports ======
# (none)

# ====== Local Project Imports ======
# (none)


class ConvertResult(BaseModel):
    """
    Output of a document conversion (office/web → PDF).

    Attributes:
        pdf_bytes (bytes): The converted PDF content.
        page_count (int): Number of pages in the converted document.
    """

    pdf_bytes: bytes
    page_count: int
