// ── Discovery types ────────────────────────────────────────────────────────

export interface ParamSchema {
  name: string
  type: string
  label?: string
  default?: unknown
  description?: string
  min?: number | null
  max?: number | null
  enum?: string[] | null
}

export interface Choice {
  id: string
  label?: string
  available: boolean
  selectable: boolean
  default?: boolean
  note?: string
  fields: ParamSchema[]
}

export type DynamicFieldKind = 'single' | 'multi' | 'optional' | 'map' | 'weights'
export type DynamicFieldScope = 'deployment' | 'collection'

export interface DynamicField {
  field_path: string
  capability?: string
  kind: DynamicFieldKind
  scope: DynamicFieldScope
  resolved: boolean
  choices: Choice[]
  note?: string
}

export interface ContractRef {
  content_type: string
  schema_ref?: string
  status?: string
}

export interface FieldDescriptor {
  name: string
  type?: string
  required?: boolean
  default?: unknown
  min?: number
  max?: number
  enum?: string[]
  description?: string
}

export interface EndpointDescriptor {
  operation: { method: string; path: string }
  route_name: string
  tags: string[]
  summary?: string
  description?: string
  path_params: FieldDescriptor[]
  query_params: FieldDescriptor[]
  input?: ContractRef
  output?: ContractRef
  dynamic_fields: DynamicField[]
}

export interface DiscoveryResponse {
  openapi_version: string
  collection_id?: string
  endpoints: EndpointDescriptor[]
  components: { schemas: Record<string, unknown> }
}

// ── Health types ───────────────────────────────────────────────────────────

export interface HealthResponse {
  status: string
  version: string
  gpu_available: boolean
  gpu_name: string | null
}

// ── Collection types ───────────────────────────────────────────────────────

export interface Collection {
  id: string
  name: string
  supported_formats: string[]
  max_file_size_bytes: number
  locality_policy: string
  embedding_model: string
  pipeline_version: string
  created_at: string
}

export interface CollectionListResponse {
  collections: Collection[]
  total: number
}

// ── Config types ───────────────────────────────────────────────────────────

export interface MetaField {
  field_name: string
  field_type: string
  required: boolean
  filterable: boolean
  lexical: boolean
  semantic: boolean
  enum_values?: string[]
  is_system: boolean
}

export interface AppliedIssue {
  code: string
  field: string
  message: string
}

export interface ConfigState {
  id: string
  name: string
  pipeline_version: string
  needs_reindex: boolean
  supported_formats: string[]
  max_file_size_bytes: number
  locality_policy: string
  embedding_model: string
  unknown_field_policy: string
  pipeline: Record<string, unknown>
  metadata_fields: MetaField[]
  created_at?: string
  applied?: {
    provided: string[]
    defaulted: string[]
    warnings: AppliedIssue[]
    notes: string[]
  }
}

export interface ConfigSchemaResponse {
  metadata_fields: MetaField[]
}

export interface ConfigVersionSummary {
  version: number
  pipeline_version: string
  note: string | null
  created_at: string
}

export interface ConfigHistoryResponse {
  collection_id: string
  total: number
  versions: ConfigVersionSummary[]
}

// ── Document types ─────────────────────────────────────────────────────────

export type DocStatus = 'pending' | 'running' | 'done' | 'error'

export interface Document {
  id: string
  collection_id: string
  source_hash: string
  filename: string
  format: string
  language?: string
  page_count?: number
  file_size: number
  status: DocStatus
  pipeline_version: string
  user_meta: Record<string, unknown>
  implicit_meta: Record<string, unknown>
  created_at: string
  chunk_count?: number
  block_count?: number
  has_original?: boolean
  has_pdf?: boolean
  has_markdown?: boolean
  indexed?: boolean
  pipeline_errors?: string[]
}

export interface DocumentListResponse {
  documents: Document[]
  total: number
  limit: number
  offset: number
}

export interface IngestResponse {
  doc_id: string
  status: string
  duplicate: boolean
  job_id?: string
}

export interface MetadataUpdateResponse {
  id: string
  user_meta: Record<string, unknown>
  changed_fields: string[]
  reindexed: boolean
  index_sync: Record<string, unknown> | null
  warning: string | null
}

export interface ReingestResponse {
  document_id: string
  job_id: string
  status: string
}

export interface DocumentDeleteResponse {
  deleted: boolean
  id: string
  qdrant_points_deleted: number
  blob_deleted: boolean
}

export interface PresignedUrlResponse {
  url: string
  expires_in: number
}

// ── Chunk types ────────────────────────────────────────────────────────────

export interface ChunkResponse {
  id: string
  document_id: string
  config_hash: string
  block_ids: string[]
  raw_text: string
  embed_text: string
  token_count: number
  strategy: string
  prov: Record<string, unknown>
  parent_id: string | null
}

export interface ChunkListResponse {
  chunks: ChunkResponse[]
  total: number
  limit: number
  offset: number
}

export interface ChunkUpdateResponse {
  id: string
  raw_text: string
  embed_text: string
  reindexed: boolean
  warning: string | null
}

// ── Page types ─────────────────────────────────────────────────────────────

export interface PageInfo {
  page: number
  n_blocks: number
  n_figures: number
  n_tables: number
  has_text: boolean
  n_chunks: number
}

export interface PageListResponse {
  document_id: string
  total_pages: number
  pages: PageInfo[]
}

export interface BlockInfo {
  id: string
  type: string
  page: number
  text: string | null
  bbox: number[]
  type_data: Record<string, unknown> | null  // FIGURE: kind/crop_key/relevance/ocr_text/description/data_table
}

export interface PageDetailResponse {
  document_id: string
  page: number
  n_blocks: number
  blocks: BlockInfo[]
  text: string
  chunk_ids: string[]
}

export interface PageReingestResponse {
  document_id: string
  page: number
  job_id: string
  note: string
}

// ── Search types ───────────────────────────────────────────────────────────

export interface SearchResultItem {
  chunk_id: string
  document_id: string
  score: number
  raw_text: string
  strategy: string
  token_count: number
  pages: number[]
  block_ids: string[]
}

export interface SearchResponse {
  collection_id: string
  query: string
  total: number
  results: SearchResultItem[]
  note?: string
}
