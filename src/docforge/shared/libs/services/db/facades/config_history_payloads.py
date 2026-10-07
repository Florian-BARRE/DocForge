# ====== Code Summary ======
# The transfer objects of the config history: ConfigAuthor is who wrote a config version (threaded
# from the request principal down to the locked snapshot write), ConfigVersionPage is one newest-first
# page of the history plus the predecessor row its oldest item is summarised against.

# ====== Standard Library Imports ======
import uuid
from dataclasses import dataclass

# ====== Internal Project Imports ======
from shared_libs.services.db.postgresql.tables import ConfigVersion


@dataclass(frozen=True, slots=True)
class ConfigAuthor:
    """
    The author stamped on a config version.

    Attributes:
        key_id (uuid.UUID | None): The authenticating API key (None for the auth-off principal).
        label (str): The write-time name snapshot (key name, "root", or "anonymous").
    """

    key_id: uuid.UUID | None
    label: str


@dataclass(slots=True)
class ConfigVersionPage:
    """
    One newest-first page of a collection's config history.

    Attributes:
        items (list[ConfigVersion]): The page rows, newest first.
        predecessor (ConfigVersion | None): The version just older than the page's last item (None when
            that item is version 1 or the page is empty) — what the last item's change is computed from.
        total (int): The number of versions in the whole history.
    """

    items: list[ConfigVersion]
    predecessor: ConfigVersion | None
    total: int


__all__ = ["ConfigAuthor", "ConfigVersionPage"]
