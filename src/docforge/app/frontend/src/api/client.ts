import type {
  ApiKeyCreatedResponse,
  ApiKeyListResponse,
  ApiKeyRevokeResponse,
  ApiKeySummary,
  CancelJobResponse,
  ChunkListResponse,
  ChunkResponse,
  ChunkUpdateResponse,
  CollectionListResponse,
  ConfigHistoryResponse,
  ConfigSchemaResponse,
  ConfigState,
  DiscoveryResponse,
  Document,
  DocumentDeleteResponse,
  DocumentListResponse,
  HealthResponse,
  IngestResponse,
  JobListResponse,
  MeResponse,
  MetagenPreviewRequest,
  MetagenPreviewResponse,
  MetadataUpdateResponse,
  MonitoringOverviewResponse,
  MonitoringResourcesResponse,
  PageDetailResponse,
  PageListResponse,
  PageReingestResponse,
  Permissions,
  PresignedUrlResponse,
  ReingestResponse,
  SearchResponse,
} from './types'
import type { SearchOverrides } from '../components/search/labTypes'

// ── HTTP error class ───────────────────────────────────────────────────────
//
// Richer than a plain Error: carries the HTTP status so callers can branch on
// specific codes (e.g. 422 validation failure) without string-matching.

/**
 * HTTP error with a status code.
 *
 * Thrown by `handleError` for all non-2xx responses except 401 (which
 * calls the unauthorized handler and throws a plain Error).
 * Use `err instanceof HttpError && err.status === 422` to detect 422s.
 */
export class HttpError extends Error {
  constructor(
    public readonly status: number,
    message: string,
  ) {
    super(message)
    this.name = 'HttpError'
  }
}

// ── Auth token registry ────────────────────────────────────────────────────
//
// The token is written here by AuthContext and read by every `request()` call
// so callers never have to thread the token through manually.
// `onUnauthorized` is registered once by AuthProvider to force-logout on 401.

let _bearerToken: string | null = null
let _onUnauthorized: (() => void) | null = null

/**
 * Registers the current bearer token so all subsequent API calls include it.
 *
 * Called by AuthContext whenever the token changes (login / logout / mount).
 *
 * Args:
 *   token: The new bearer token, or null when logged out.
 */
export function setAuthToken(token: string | null): void {
  _bearerToken = token
}

/**
 * Registers a callback that fires when any API call receives a 401.
 *
 * The callback is responsible for logging the user out.  It is registered once
 * by AuthProvider and is not expected to change.
 *
 * Args:
 *   cb: Function to invoke on a 401 response from the API.
 */
export function setUnauthorizedHandler(cb: () => void): void {
  _onUnauthorized = cb
}

// Strip redacted sentinels and undefined values recursively before sending to the backend.
// The backend echoes secrets as "•••" in config state; sending that back would overwrite
// the real value with the literal placeholder string.
function stripRedacted(v: unknown): unknown {
  if (v === '•••' || v === undefined) return undefined
  if (Array.isArray(v)) {
    const cleaned = v.map(stripRedacted).filter(x => x !== undefined)
    return cleaned
  }
  if (v !== null && typeof v === 'object') {
    const out: Record<string, unknown> = {}
    for (const [k, val] of Object.entries(v as Record<string, unknown>)) {
      const cleaned = stripRedacted(val)
      if (cleaned !== undefined) out[k] = cleaned
    }
    return out
  }
  return v
}

// Builds the Authorization header when a bearer token is present.
// Returns a typed Record so it spreads cleanly into fetch HeadersInit.
function authHeaders(): Record<string, string> {
  return _bearerToken ? { Authorization: `Bearer ${_bearerToken}` } : {}
}

// Handles the common "not-ok" path after a fetch: 401 triggers force-logout,
// everything else throws an HttpError with the status code and backend detail.
async function handleError(res: Response): Promise<never> {
  if (res.status === 401) {
    // Token is missing or expired — force the user back to the login screen.
    // A 403 is NOT treated as a logout signal; it is surfaced as a normal error.
    _onUnauthorized?.()
    throw new Error('Session expired. Please log in again.')
  }
  const body = await res.json().catch(() => ({}))
  const msg = (body as { detail?: unknown })?.detail ?? `HTTP ${res.status}`
  throw new HttpError(res.status, typeof msg === 'string' ? msg : JSON.stringify(msg))
}

// Base fetch with consistent error handling and bearer-token injection.
async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const hasBody = init?.body != null
  const headers: Record<string, string> = {
    ...authHeaders(),
    ...(hasBody ? { 'Content-Type': 'application/json' } : {}),
    ...(init?.headers as Record<string, string> | undefined),
  }
  const res = await fetch(`/api/v1${path}`, { ...init, headers })
  if (!res.ok) return handleError(res)
  return res.json() as Promise<T>
}

// Multipart form request (for file upload) — also injects the bearer token.
async function upload<T>(path: string, form: FormData): Promise<T> {
  const res = await fetch(`/api/v1${path}`, {
    method: 'POST',
    headers: authHeaders(),
    body: form,
  })
  if (!res.ok) return handleError(res)
  return res.json() as Promise<T>
}

// ── Health ─────────────────────────────────────────────────────────────────

export const getHealth = (): Promise<HealthResponse> =>
  request<HealthResponse>('/health/ping')

// ── Discovery ──────────────────────────────────────────────────────────────

export const getDiscovery = (collectionId?: string): Promise<DiscoveryResponse> => {
  const qs = collectionId ? `?collection_id=${collectionId}` : ''
  return request<DiscoveryResponse>(`/discovery${qs}`)
}

// ── Collections ────────────────────────────────────────────────────────────

export const listCollections = (): Promise<CollectionListResponse> =>
  request<CollectionListResponse>('/collections/list')

// Single collection lookup — useful when the inspector needs the persisted
// resolved pipeline (collection.pipeline) without going through config_state.
export const getCollection = async (id: string): Promise<import('./types').Collection> => {
  const list = await listCollections()
  const found = list.collections.find(c => c.id === id)
  if (!found) throw new Error(`Collection ${id} not found`)
  return found
}

export const createCollection = (body: Record<string, unknown>): Promise<ConfigState> =>
  request<ConfigState>('/collections/create', {
    method: 'POST',
    body: JSON.stringify(stripRedacted(body)),
  })

export const deleteCollection = (id: string): Promise<{ deleted: boolean; id: string }> =>
  request(`/collections/${id}/delete`, { method: 'DELETE' })

// ── Config ─────────────────────────────────────────────────────────────────

export const getConfigState = (collectionId: string): Promise<ConfigState> =>
  request<ConfigState>(`/collections/${collectionId}/config/state`)

export const getConfigSchema = (collectionId: string): Promise<ConfigSchemaResponse> =>
  request<ConfigSchemaResponse>(`/collections/${collectionId}/config/schema`)

export const getConfigHistory = (collectionId: string): Promise<ConfigHistoryResponse> =>
  request<ConfigHistoryResponse>(`/collections/${collectionId}/config/history`)

export const updateConfig = (
  collectionId: string,
  patch: Record<string, unknown>,
  note?: string,
): Promise<ConfigState> =>
  request<ConfigState>(`/collections/${collectionId}/config/update`, {
    method: 'POST',
    body: JSON.stringify({ patch: stripRedacted(patch), note }),
  })

export const rollbackConfig = (collectionId: string, version: number): Promise<ConfigState> =>
  request<ConfigState>(`/collections/${collectionId}/config/rollback`, {
    method: 'POST',
    body: JSON.stringify({ version }),
  })

// ── Documents ──────────────────────────────────────────────────────────────

export const listDocuments = (
  collectionId: string,
  params?: {
    limit?: number
    offset?: number
    status?: string
    sort_by?: string
    sort_order?: 'asc' | 'desc'
  },
): Promise<DocumentListResponse> => {
  const qs = new URLSearchParams()
  if (params?.limit  != null) qs.set('limit',      String(params.limit))
  if (params?.offset != null) qs.set('offset',     String(params.offset))
  if (params?.status)         qs.set('status',     params.status)
  if (params?.sort_by)        qs.set('sort_by',    params.sort_by)
  if (params?.sort_order)     qs.set('sort_order', params.sort_order)
  const q = qs.toString() ? `?${qs}` : ''
  return request<DocumentListResponse>(`/collections/${collectionId}/documents/list${q}`)
}

export const getDocument = (collectionId: string, docId: string): Promise<Document> =>
  request<Document>(`/collections/${collectionId}/documents/${docId}`)

// ── Real-time streams (SSE, brique C) ───────────────────────────────────────

// Live job/stage updates scoped to one collection's documents — replaces 2 s polling in
// DocumentsTab. EventSource auto-reconnects natively; callers fall back to polling on `onerror`.
// Note: EventSource does not support custom headers.  The bearer token is sent as a
// `token` query parameter; the backend auth middleware must accept it alongside the
// Authorization header for SSE endpoints.  If the backend does not yet support this,
// the SSE stream will fall back to unauthenticated (polling remains available).
export const streamCollectionDocuments = (collectionId: string): EventSource => {
  const qs = _bearerToken ? `?token=${encodeURIComponent(_bearerToken)}` : ''
  return new EventSource(`/api/v1/collections/${collectionId}/documents/stream${qs}`)
}

// Global monitoring event stream (jobs, stages, workers, batches) for the Monitoring tab.
export const streamMonitoring = (): EventSource => {
  const qs = _bearerToken ? `?token=${encodeURIComponent(_bearerToken)}` : ''
  return new EventSource(`/api/v1/monitoring/stream${qs}`)
}

export const ingestDocument = (
  collectionId: string,
  file: File,
  metadata?: Record<string, unknown>,
): Promise<IngestResponse> => {
  const form = new FormData()
  form.append('file', file)
  if (metadata && Object.keys(metadata).length > 0) {
    form.append('metadata', JSON.stringify(metadata))
  }
  return upload<IngestResponse>(`/collections/${collectionId}/documents/ingest`, form)
}

export const updateDocument = (
  collectionId: string,
  docId: string,
  metadata: Record<string, unknown>,
  reindex = false,
): Promise<MetadataUpdateResponse> =>
  request<MetadataUpdateResponse>(`/collections/${collectionId}/documents/${docId}/update`, {
    method: 'POST',
    body: JSON.stringify({ metadata, reindex }),
  })

export const reingestDocument = (
  collectionId: string,
  docId: string,
  force = false,
): Promise<ReingestResponse> =>
  request<ReingestResponse>(`/collections/${collectionId}/documents/${docId}/reingest`, {
    method: 'POST',
    body: JSON.stringify({ force }),
  })

export const deleteDocument = (
  collectionId: string,
  docId: string,
): Promise<DocumentDeleteResponse> =>
  request<DocumentDeleteResponse>(`/collections/${collectionId}/documents/${docId}/delete`, {
    method: 'DELETE',
  })

// ── Document files (pre-signed URLs) ───────────────────────────────────────

export const getDocumentOriginal = (collectionId: string, docId: string): Promise<PresignedUrlResponse> =>
  request<PresignedUrlResponse>(`/collections/${collectionId}/documents/${docId}/original`)

export const getDocumentMarkdown = (collectionId: string, docId: string): Promise<PresignedUrlResponse> =>
  request<PresignedUrlResponse>(`/collections/${collectionId}/documents/${docId}/markdown`)

export const getDocumentPdf = (collectionId: string, docId: string): Promise<PresignedUrlResponse> =>
  request<PresignedUrlResponse>(`/collections/${collectionId}/documents/${docId}/pdf`)

// ── Chunks ─────────────────────────────────────────────────────────────────

export const listChunks = (
  collectionId: string,
  docId: string,
  params?: { limit?: number; offset?: number },
): Promise<ChunkListResponse> => {
  const qs = new URLSearchParams()
  if (params?.limit  != null) qs.set('limit',  String(params.limit))
  if (params?.offset != null) qs.set('offset', String(params.offset))
  const q = qs.toString() ? `?${qs}` : ''
  return request<ChunkListResponse>(`/collections/${collectionId}/documents/${docId}/chunks/list${q}`)
}

export const getChunk = (
  collectionId: string,
  docId: string,
  chunkId: string,
): Promise<ChunkResponse> =>
  request<ChunkResponse>(`/collections/${collectionId}/documents/${docId}/chunks/${chunkId}`)

export const updateChunk = (
  collectionId: string,
  docId: string,
  chunkId: string,
  body: { raw_text?: string; embed_text?: string; reindex?: boolean },
): Promise<ChunkUpdateResponse> =>
  request<ChunkUpdateResponse>(
    `/collections/${collectionId}/documents/${docId}/chunks/${chunkId}/update`,
    { method: 'POST', body: JSON.stringify(body) },
  )

// ── Document block assets ──────────────────────────────────────────────────

export const getBlockFigure = (
  collectionId: string,
  docId: string,
  blockId: string,
): Promise<PresignedUrlResponse> =>
  request<PresignedUrlResponse>(
    `/collections/${collectionId}/documents/${docId}/figures/${encodeURIComponent(blockId)}`
  )

// ── Pages ──────────────────────────────────────────────────────────────────

export const listPages = (collectionId: string, docId: string): Promise<PageListResponse> =>
  request<PageListResponse>(`/collections/${collectionId}/documents/${docId}/pages/list`)

export const getPage = (
  collectionId: string,
  docId: string,
  pageNumber: number,
): Promise<PageDetailResponse> =>
  request<PageDetailResponse>(`/collections/${collectionId}/documents/${docId}/pages/${pageNumber}`)

export const getPageScreenshotUrl = (collectionId: string, docId: string, pageNumber: number): string => {
  const base = `/api/v1/collections/${collectionId}/documents/${docId}/pages/${pageNumber}/screenshot`
  // The browser loads this via <img src>, which cannot send the Authorization header — so the
  // bearer is passed as ?token= (the screenshot route accepts it via the media auth gate).
  // Omitted when logged out / auth disabled.
  return _bearerToken ? `${base}?token=${encodeURIComponent(_bearerToken)}` : base
}

export const reingestPage = (
  collectionId: string,
  docId: string,
  pageNumber: number,
): Promise<PageReingestResponse> =>
  request<PageReingestResponse>(
    `/collections/${collectionId}/documents/${docId}/pages/${pageNumber}/reingest`,
    { method: 'POST' },
  )

// ── Search ─────────────────────────────────────────────────────────────────

export const searchDocuments = (
  collectionId: string,
  query: string,
  opts?: {
    top_k?: number
    filters?: Record<string, unknown>
    weights?: Record<string, number>
    /** When true, each result carries vector_ranks with per-vector rank breakdown. */
    debug?: boolean
    /**
     * Per-query overrides that shadow the collection's saved pipeline.search config.
     * Only send the keys that the user explicitly changed — omit a key to use the
     * saved config value.  A 422 is returned when the override is incompatible with
     * the collection's provider setup (e.g. rerank with no rerank chain).
     */
    overrides?: SearchOverrides
  },
): Promise<SearchResponse> =>
  request<SearchResponse>(`/collections/${collectionId}/documents/search`, {
    method: 'POST',
    body: JSON.stringify({ query, ...opts }),
  })

export const searchWithinDocument = (
  collectionId: string,
  docId: string,
  query: string,
  opts?: {
    top_k?: number
    filters?: Record<string, unknown>
    weights?: Record<string, number>
    /** When true, each result carries vector_ranks with per-vector rank breakdown. */
    debug?: boolean
    /**
     * Per-query overrides — same semantics as {@link searchDocuments}.
     * A 422 is returned when the override conflicts with the collection's config.
     */
    overrides?: SearchOverrides
  },
): Promise<SearchResponse> =>
  request<SearchResponse>(`/collections/${collectionId}/documents/${docId}/search`, {
    method: 'POST',
    body: JSON.stringify({ query, ...opts }),
  })

// ── Auth ───────────────────────────────────────────────────────────────────
// Note: login() is handled directly in AuthContext to avoid a circular
// dependency (the context owns the token; the client reads it).
// All other auth endpoints go through the standard request() helper.

/** Returns the current root user's identity. */
export const getMe = (): Promise<MeResponse> =>
  request<MeResponse>('/auth/me')

// ── API keys ───────────────────────────────────────────────────────────────
//
// AUTH-B: permissions is now REQUIRED on key creation.
// The plaintext key is only present in ApiKeyCreatedResponse (creation only).

/**
 * Creates a new API key with the given name and permission scope.
 *
 * The plaintext key value is present in the response exactly once and cannot
 * be retrieved again — display it immediately and prompt the user to copy it.
 *
 * Args:
 *   name:        Human-readable label for the key (e.g. "ci-pipeline").
 *   permissions: Scope entries granting capabilities per collection.
 */
export const createApiKey = (name: string, permissions: Permissions): Promise<ApiKeyCreatedResponse> =>
  request<ApiKeyCreatedResponse>('/auth/keys', {
    method: 'POST',
    body: JSON.stringify({ name, permissions }),
  })

/** Lists all API keys (active + revoked) with their permission scopes. */
export const listApiKeys = (): Promise<ApiKeyListResponse> =>
  request<ApiKeyListResponse>('/auth/keys')

/** Revokes a single API key by its UUID. */
export const revokeApiKey = (keyId: string): Promise<ApiKeyRevokeResponse> =>
  request<ApiKeyRevokeResponse>(`/auth/keys/${keyId}`, { method: 'DELETE' })

// Re-export the ApiKeySummary type for callers that import from client.ts.
export type { ApiKeySummary }

// ── Monitoring ─────────────────────────────────────────────────────────────

/** Fetches aggregate queue + workers overview. */
export const getMonitoringOverview = (): Promise<MonitoringOverviewResponse> =>
  request<MonitoringOverviewResponse>('/monitoring/overview')

/** Fetches device capabilities, admission limits, and queue depth. */
export const getMonitoringResources = (): Promise<MonitoringResourcesResponse> =>
  request<MonitoringResourcesResponse>('/monitoring/resources')

/**
 * Lists jobs with optional status filter and pagination.
 *
 * Args:
 *   params.limit:  Max rows to return.
 *   params.offset: Row offset for pagination.
 *   params.status: Filter by job status (pending / running / done / failed).
 */
export const listJobs = (params?: {
  limit?: number
  offset?: number
  status?: string
}): Promise<JobListResponse> => {
  const qs = new URLSearchParams()
  if (params?.limit  != null) qs.set('limit',  String(params.limit))
  if (params?.offset != null) qs.set('offset', String(params.offset))
  if (params?.status)         qs.set('status', params.status)
  const q = qs.toString() ? `?${qs}` : ''
  return request<JobListResponse>(`/jobs${q}`)
}

/**
 * Cancels a queued or running job.
 *
 * Args:
 *   id: UUID of the job to cancel.
 */
export const cancelJob = (id: string): Promise<CancelJobResponse> =>
  request<CancelJobResponse>(`/jobs/${id}/cancel`, { method: 'POST' })

// ── Metagen preview (S5b) ──────────────────────────────────────────────────
//
// Dry-run preview: generate a single metadata value via the configured LLM chain
// for one field/chunk pair without running a full ingestion.
// Requires CONFIG_WRITE capability. Returns 422 when no chain or target is set.

/**
 * Preview LLM metadata generation for one field using sample text or a stored chunk.
 *
 * Args:
 *   collectionId: Target collection.
 *   body:         Preview request — field_name + exactly one of chunk_id / sample_text.
 *
 * Returns:
 *   MetagenPreviewResponse: Generated value, token/cost estimate, provider, degraded flag.
 */
export const previewMetagen = (
  collectionId: string,
  body: MetagenPreviewRequest,
): Promise<MetagenPreviewResponse> =>
  request<MetagenPreviewResponse>(`/collections/${collectionId}/metagen/preview`, {
    method: 'POST',
    body: JSON.stringify(body),
  })
