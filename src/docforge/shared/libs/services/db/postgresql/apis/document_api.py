# ====== Code Summary ======
# DocumentApi — the public data-access facade for the document domain: the catalogue record, its
# metadata VALUES and its pages (dedup lookup, ingestion status transitions included). The
# implementation is split by responsibility into ``apis/documents/``; this class only re-exposes
# every public method under its historical name, so callers (the facades, the tests) keep importing
# ``DocumentApi`` from here and monkeypatching its attributes unchanged.
#
#   DocumentRowApi        the core document row: lookups, listings, counts, status, toggle, delete
#   DocumentMetadataApi   the metadata values: reads, filterable / searchable selects, writes
#   DocumentPageApi       the document's pages

# ====== Internal Project Imports ======
from .documents import DocumentMetadataApi, DocumentPageApi, DocumentRowApi


class DocumentApi:
    """Static facade over the document data-access APIs of ``apis/documents/`` (one name per method)."""

    def __new__(cls, *args: object, **kwargs: object) -> None:
        raise TypeError("DocumentApi is a static-only class and cannot be instantiated.")

    # ---- DocumentRowApi
    create = staticmethod(DocumentRowApi.create)
    get = staticmethod(DocumentRowApi.get)
    get_for_update = staticmethod(DocumentRowApi.get_for_update)
    get_by_ids = staticmethod(DocumentRowApi.get_by_ids)
    find = staticmethod(DocumentRowApi.find)
    list_for_collection = staticmethod(DocumentRowApi.list_for_collection)
    count_for_collection = staticmethod(DocumentRowApi.count_for_collection)
    count_by_collections = staticmethod(DocumentRowApi.count_by_collections)
    set_status = staticmethod(DocumentRowApi.set_status)
    finalize_done = staticmethod(DocumentRowApi.finalize_done)
    flag_replay_failure = staticmethod(DocumentRowApi.flag_replay_failure)
    mark_processing = staticmethod(DocumentRowApi.mark_processing)
    set_enabled = staticmethod(DocumentRowApi.set_enabled)
    set_enabled_many = staticmethod(DocumentRowApi.set_enabled_many)
    list_disabled_ids = staticmethod(DocumentRowApi.list_disabled_ids)
    list_enabled_ids = staticmethod(DocumentRowApi.list_enabled_ids)
    update_facts = staticmethod(DocumentRowApi.update_facts)
    delete = staticmethod(DocumentRowApi.delete)
    delete_many = staticmethod(DocumentRowApi.delete_many)
    # ---- DocumentMetadataApi
    get_metadata = staticmethod(DocumentMetadataApi.get_metadata)
    get_metadata_with_names = staticmethod(DocumentMetadataApi.get_metadata_with_names)
    get_metadata_for_documents = staticmethod(DocumentMetadataApi.get_metadata_for_documents)
    get_filterable_metadata = staticmethod(DocumentMetadataApi.get_filterable_metadata)
    get_filterable_metadata_for_documents = staticmethod(
        DocumentMetadataApi.get_filterable_metadata_for_documents
    )
    get_chunk_filterable_metadata = staticmethod(DocumentMetadataApi.get_chunk_filterable_metadata)
    get_searchable_metadata = staticmethod(DocumentMetadataApi.get_searchable_metadata)
    replace_metadata = staticmethod(DocumentMetadataApi.replace_metadata)
    touch = staticmethod(DocumentMetadataApi.touch)
    update_metadata = staticmethod(DocumentMetadataApi.update_metadata)
    delete_metadata = staticmethod(DocumentMetadataApi.delete_metadata)
    # ---- DocumentPageApi
    replace_pages = staticmethod(DocumentPageApi.replace_pages)
    get_pages = staticmethod(DocumentPageApi.get_pages)


__all__ = ["DocumentApi"]
