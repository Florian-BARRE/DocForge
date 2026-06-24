# ---------------------- Model --------------------- #
from .models import ContentPack

# ------------------- Content packs ---------------- #
from .fr import CONTRACT_FR, REPORT_FR
from .en import CONTRACT_EN, REPORT_EN
from .es import CONTRACT_ES, REPORT_ES

# Lookup: (doc_type, language) -> ContentPack
_PACKS: dict[tuple[str, str], ContentPack] = {
    ("contract", "fr"): CONTRACT_FR, ("report", "fr"): REPORT_FR,
    ("contract", "en"): CONTRACT_EN, ("report", "en"): REPORT_EN,
    ("contract", "es"): CONTRACT_ES, ("report", "es"): REPORT_ES,
}


def get_content(doc_type: str, language: str) -> ContentPack:
    """
    Return the content pack for a document archetype + language.

    Args:
        doc_type (str): "contract" or "report".
        language (str): "fr" / "en" / "es".

    Returns:
        ContentPack: The matching pack.

    Raises:
        KeyError: If no pack exists for the (doc_type, language) pair.
    """
    try:
        return _PACKS[(doc_type, language)]
    except KeyError as exc:
        raise KeyError(f"No content pack for doc_type={doc_type!r} language={language!r}.") from exc


# ------------------- Public API ------------------- #
__all__ = [
    "ContentPack",
    "get_content",
    "CONTRACT_FR", "REPORT_FR",
    "CONTRACT_EN", "REPORT_EN",
    "CONTRACT_ES", "REPORT_ES",
]
