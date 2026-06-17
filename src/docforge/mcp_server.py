#!/usr/bin/env python3
# ====== Code Summary ======
# Standalone MCP (Model Context Protocol) server for DocForge.
# Exposes document intelligence tools via stdio transport for Claude Code / Claude Desktop.
#
# Configuration:
#   DOCFORGE_API_URL  Base URL of the DocForge REST API (default: http://localhost:8000)
#
# Usage:
#   python mcp_server.py                  # reads DOCFORGE_API_URL from env
#   DOCFORGE_API_URL=http://... python mcp_server.py
#
# Tools exposed:
#   - list_collections   : list all collections
#   - list_documents     : list documents in a collection
#   - search_documents   : hybrid semantic search in a collection
#   - get_document       : get full details for a document
#   - ingest_document    : upload and index a local file into a collection
#   - create_collection  : create a new collection with sensible defaults
#   - reindex_collection : trigger reindexing of all done documents in a collection

# ====== Standard Library Imports ======
import pathlib

# ====== Third-Party Library Imports ======
import httpx
from configplusplus import EnvConfigLoader, env
from loggerplusplus import LoggerClass
from mcp.server.fastmcp import FastMCP


# ─── Configuration ────────────────────────────────────────────────────────────


class McpConfig(EnvConfigLoader):
    """
    Environment-driven configuration for the DocForge MCP server.

    All values are read from environment variables at import time.
    Missing variables with defaults fall back silently.
    """

    # Base URL of the DocForge REST API — override via DOCFORGE_API_URL env var.
    DOCFORGE_API_URL: str = env("DOCFORGE_API_URL", default="http://localhost:8000")


# ─── HTTP client ──────────────────────────────────────────────────────────────


class DocForgeApiClient(LoggerClass):
    """
    HTTP client for the DocForge REST API.

    Provides typed helpers for GET, POST, and multipart file upload,
    all rooted at the /api/v1 prefix of the configured base URL.
    A single persistent AsyncClient is reused across calls for connection pooling.
    """

    def __init__(self, base_url: str) -> None:
        """
        Initialise the client and bind the /api/v1 prefix.

        Args:
            base_url (str): Base URL of the DocForge service, e.g. 'http://localhost:8000'.
        """
        LoggerClass.__init__(self)
        # Store the versioned API root used by all endpoint helpers.
        self._api_v1: str = f"{base_url.rstrip('/')}/api/v1"
        # Persistent async client — connection pooling across tool calls.
        self._http: httpx.AsyncClient = httpx.AsyncClient(timeout=60.0)
        self.logger.info(f"DocForgeApiClient initialised — base: {self._api_v1}")

    async def get(self, path: str) -> dict:
        """
        Perform a GET request against the DocForge API.

        Args:
            path (str): API path relative to /api/v1, e.g. '/collections'.

        Returns:
            dict: Parsed JSON response body.

        Raises:
            RuntimeError: If the server returns a non-2xx status code.
        """
        # 1. Issue the GET request
        res = await self._http.get(f"{self._api_v1}{path}")

        # 2. Raise on non-success status
        if not res.is_success:
            raise RuntimeError(f"DocForge API error {res.status_code}: {res.text[:200]}")

        # 3. Parse and return JSON body
        return res.json()

    async def post(self, path: str, body: dict) -> dict:
        """
        Perform a POST request with a JSON body against the DocForge API.

        Args:
            path (str): API path relative to /api/v1, e.g. '/collections/{id}/search'.
            body (dict): JSON-serialisable request body.

        Returns:
            dict: Parsed JSON response body, or an empty dict for 204 No Content.

        Raises:
            RuntimeError: If the server returns a non-2xx status code.
        """
        # 1. Issue the POST request with the JSON body
        res = await self._http.post(f"{self._api_v1}{path}", json=body)

        # 2. Raise on non-success status
        if not res.is_success:
            raise RuntimeError(f"DocForge API error {res.status_code}: {res.text[:200]}")

        # 3. Return empty dict for 204 No Content (no body to parse)
        if res.status_code == 204:
            return {}

        # 4. Parse and return JSON body
        return res.json()

    async def ingest(self, collection_id: str, file_path: str) -> dict:
        """
        Upload a local file into a DocForge collection via multipart/form-data.

        A dedicated short-lived AsyncClient with a longer timeout is used for
        file uploads to avoid blocking the shared connection pool.

        Args:
            collection_id (str): UUID of the target collection.
            file_path (str): Absolute path to the local file to upload.

        Returns:
            dict: Ingest response with fields doc_id, status, duplicate, job_id.

        Raises:
            FileNotFoundError: If file_path does not exist on disk.
            ValueError: If file_path points to a directory rather than a file.
            RuntimeError: If the server returns a non-2xx status code.
        """
        # 1. Validate the local path before touching the network
        path = pathlib.Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")
        if not path.is_file():
            raise ValueError(f"Path is not a file: {file_path}")

        # 2. Upload via multipart/form-data using a dedicated client with a
        #    longer timeout — file uploads can be slow on large documents.
        async with httpx.AsyncClient(timeout=120.0) as client:
            with path.open("rb") as fh:
                res = await client.post(
                    f"{self._api_v1}/collections/{collection_id}/documents",
                    files={"file": (path.name, fh, "application/octet-stream")},
                )

        # 3. Raise on non-success status
        if not res.is_success:
            raise RuntimeError(f"DocForge ingest error {res.status_code}: {res.text[:200]}")

        # 4. Return the ingest response payload
        return res.json()


# ─── Module-level singletons ──────────────────────────────────────────────────

# Shared API client — instantiated once, reused across all tool calls.
_client: DocForgeApiClient = DocForgeApiClient(McpConfig.DOCFORGE_API_URL)

# MCP application — tool decorators register handlers on this instance.
mcp: FastMCP = FastMCP(
    name="DocForge",
    instructions=(
        "DocForge is a document intelligence platform. "
        "Use these tools to manage collections of documents and perform "
        "hybrid semantic search over their indexed content."
    ),
)


# ─── Tools ────────────────────────────────────────────────────────────────────


@mcp.tool()
async def list_collections() -> list[dict]:
    """
    List all document collections in DocForge.

    Returns a list of collection objects, each with fields:
    - id (str): Collection UUID.
    - name (str): Human-readable name.
    - pipeline_version (str): Current pipeline version tag.
    - supported_formats (list[str]): Accepted file extensions.
    - embedding_model (str): Model used for semantic search.
    - created_at (str): ISO-8601 creation timestamp.

    Returns:
        list[dict]: All collections.
    """
    # 1. Call the collections list endpoint and unpack the wrapper key
    data = await _client.get("/collections")
    return data.get("collections", [])


@mcp.tool()
async def list_documents(collection_id: str, status: str = "") -> list[dict]:
    """
    List documents in a collection.

    Args:
        collection_id (str): UUID of the target collection.
        status (str): Optional status filter — one of 'pending', 'running', 'done', 'failed'.
                      Empty string returns all statuses.

    Returns:
        list[dict]: Documents with fields: id, filename, format, status,
                    page_count, file_size, language, created_at.
    """
    # 1. Fetch all documents for the collection
    docs: list[dict] = await _client.get(f"/collections/{collection_id}/documents")

    # 2. Apply optional status filter when provided
    if status:
        docs = [d for d in docs if d.get("status") == status]

    return docs


@mcp.tool()
async def get_document(document_id: str) -> dict:
    """
    Get full details for a document by its ID.

    Args:
        document_id (str): UUID of the document.

    Returns:
        dict: Full document record including metadata, status, pipeline_version,
              implicit_meta, and user_meta fields.
    """
    # 1. Fetch and return the document record directly
    return await _client.get(f"/documents/{document_id}")


@mcp.tool()
async def search_documents(
    collection_id: str,
    query: str,
    top_k: int = 10,
) -> dict:
    """
    Perform hybrid semantic search over indexed document chunks in a collection.

    Uses BGE-M3 embeddings with Qdrant RRF fusion (dense + sparse BM25).
    Only documents with status='done' that have been indexed are searchable.

    Args:
        collection_id (str): UUID of the collection to search.
        query (str): Natural language search query.
        top_k (int): Maximum number of results to return (default 10, max 50).

    Returns:
        dict: Search response with fields:
              - query (str): The query string.
              - total (int): Number of results returned.
              - results (list[dict]): Ranked chunks, each with:
                  chunk_id, document_id, score (0–1), raw_text,
                  strategy, token_count, pages, block_ids.
    """
    # 1. Clamp top_k to the accepted [1, 50] range
    top_k = max(1, min(top_k, 50))

    # 2. Post search request to the collection search endpoint
    return await _client.post(
        f"/collections/{collection_id}/search",
        {"query": query, "top_k": top_k},
    )


@mcp.tool()
async def ingest_document(collection_id: str, file_path: str) -> dict:
    """
    Upload a local file into a DocForge collection and start indexing.

    The file is uploaded via multipart/form-data. Processing happens
    asynchronously — use get_document() to poll the status until 'done'.

    Args:
        collection_id (str): UUID of the target collection.
        file_path (str): Absolute path to the local file to upload.
                         Supported formats: PDF, DOCX, DOC, XLSX, PPTX, ODT, TXT, MD.

    Returns:
        dict: Ingest response with fields:
              - doc_id (str): UUID of the created document.
              - status (str): Initial status ('pending' or 'done' for duplicates).
              - duplicate (bool): True if an identical file was already indexed.
              - job_id (str | null): arq job ID (null for duplicates / dry_run).
    """
    # 1. Delegate file validation and upload to the API client
    return await _client.ingest(collection_id, file_path)


@mcp.tool()
async def create_collection(name: str) -> dict:
    """
    Create a new document collection.

    Sensible defaults are applied automatically:
    - supported_formats: pdf, docx, doc, xlsx, pptx, ppt, odt
    - max_file_size_bytes: 100 MB (104 857 600 bytes)
    - locality_policy: external_allowed (cloud providers permitted)
    - embedding_model: BAAI/bge-m3 (dense + sparse BM25 hybrid)
    - unknown_field_policy: ignore (extra metadata fields are silently dropped)

    Args:
        name (str): Human-readable name for the collection.

    Returns:
        dict: The created Collection object (id, name, pipeline_version, …).
    """
    # 1. Post the collection creation request with default platform settings
    return await _client.post(
        "/collections",
        {
            "name": name,
            "supported_formats": ["pdf", "docx", "doc", "xlsx", "pptx", "ppt", "odt"],
            "max_file_size_bytes": 100 * 1024 * 1024,
            "locality_policy": "external_allowed",
            "embedding_model": "BAAI/bge-m3",
            "unknown_field_policy": "ignore",
            "pipeline": {},
        },
    )


@mcp.tool()
async def reindex_collection(collection_id: str, force: bool = False) -> dict:
    """
    Trigger reindexing of all done documents in a collection.

    Stage cache prevents re-parsing unchanged documents. Use force=True
    to delete existing chunks and rebuild the index from scratch.

    Args:
        collection_id (str): UUID of the collection to reindex.
        force (bool): If True, delete existing chunks before reindexing.

    Returns:
        dict: Reindex response with fields:
              - collection_id (str)
              - documents_enqueued (int): Number of jobs submitted.
              - message (str): Human-readable summary.
    """
    # 1. Post the reindex request with the force flag
    return await _client.post(
        f"/collections/{collection_id}/reindex",
        {"force": force},
    )


# ─── Entry point ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    # Run the MCP server over stdio (Claude Code / Claude Desktop transport)
    mcp.run(transport="stdio")
