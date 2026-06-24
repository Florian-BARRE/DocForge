import type {
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
  MetadataUpdateResponse,
  PageDetailResponse,
  PageListResponse,
  PageReingestResponse,
  PresignedUrlResponse,
  ReingestResponse,
  SearchResponse,
} from './types'

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

// Base fetch with consistent error handling.
async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const hasBody = init?.body != null
  const res = await fetch(`/api/v1${path}`, {
    headers: {
      ...(hasBody ? { 'Content-Type': 'application/json' } : {}),
      ...init?.headers,
    },
    ...init,
  })
  if (!res.ok) {
    const body = await res.json().catch(() => ({}))
    const msg = body?.detail ?? `HTTP ${res.status}`
    throw new Error(typeof msg === 'string' ? msg : JSON.stringify(msg))
  }
  return res.json() as Promise<T>
}

// Multipart form request (for file upload).
async function upload<T>(path: string, form: FormData): Promise<T> {
  const res = await fetch(`/api/v1${path}`, { method: 'POST', body: form })
  if (!res.ok) {
    const body = await res.json().catch(() => ({}))
    const msg = body?.detail ?? `HTTP ${res.status}`
    throw new Error(typeof msg === 'string' ? msg : JSON.stringify(msg))
  }
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
export const streamCollectionDocuments = (collectionId: string): EventSource =>
  new EventSource(`/api/v1/collections/${collectionId}/documents/stream`)

// Global monitoring event stream (jobs, stages, workers, batches) for the Monitoring tab.
export const streamMonitoring = (): EventSource =>
  new EventSource('/api/v1/monitoring/stream')

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

export const getPageScreenshotUrl = (collectionId: string, docId: string, pageNumber: number): string =>
  `/api/v1/collections/${collectionId}/documents/${docId}/pages/${pageNumber}/screenshot`

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
  },
): Promise<SearchResponse> =>
  request<SearchResponse>(`/collections/${collectionId}/documents/${docId}/search`, {
    method: 'POST',
    body: JSON.stringify({ query, ...opts }),
  })
