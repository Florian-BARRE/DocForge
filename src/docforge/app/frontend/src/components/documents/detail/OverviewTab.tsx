// ====== Code Summary ======
// OverviewTab — sectioned metadata view using <ValueRenderer> for every value.
// Never dumps "[object Object]" or raw arrays. Internal keys (fingerprints /
// storage paths) are hidden behind a toggle. Chain traces are summarised.

import { ReactNode, useState } from 'react'

import type { Document } from '../../../api/types'
import type { KVEntry } from '../../ui/primitives/KeyValueGrid'
import { KeyValueGrid } from '../../ui/primitives/KeyValueGrid'
import { SectionHeader } from '../../ui/primitives/SectionHeader'
import { ValueRenderer } from '../../ui/ValueRenderer'
import { formatDuration, formatFileSize } from './detailHelpers'
import {
  countArr, formatBudget, humanize,
  INTERNAL_IMPLICIT, SKIP_IMPLICIT,
} from './overviewMeta'

// ── Section wrapper ───────────────────────────────────────────────────────────

interface SectionBlockProps {
  title: string
  entries: KVEntry[]
  action?: ReactNode
  children?: ReactNode
}

/**
 * Section container: header + optional KV grid + optional extra children.
 * Returns null when there is nothing to render (empty entries, no children, no action).
 * An action prop (e.g. a toggle button) causes the header to always render.
 */
function SectionBlock({ title, entries, action, children }: SectionBlockProps) {
  if (entries.length === 0 && !children && !action) return null
  return (
    <div className="overview-section">
      <SectionHeader action={action}>{title}</SectionHeader>
      {entries.length > 0 && <KeyValueGrid entries={entries} keyWidth={150} />}
      {children}
    </div>
  )
}

// ── Props ─────────────────────────────────────────────────────────────────────

interface OverviewTabProps {
  doc: Document
  pipelineDurationMs: number | null | undefined
  /** Callback to switch the parent DocDetailView to the Chain traces tab. */
  onViewTraces?: () => void
}

// ── Component ─────────────────────────────────────────────────────────────────

/**
 * Renders document metadata in labelled sections.
 *
 * Sections: Identity / Content & structure / Processing /
 * User metadata / Advanced (collapsed) / Chain traces summary.
 *
 * All values route through <ValueRenderer>; booleans become badges, hex
 * hashes are truncated, arrays of objects never produce "[object Object]".
 * quality_score is deduplicated (top-level shown, implicit_meta entry skipped).
 *
 * Args:
 *   doc:               Fully hydrated document record.
 *   pipelineDurationMs: Wall-clock pipeline time in milliseconds.
 *   onViewTraces:      Navigate to the Chain traces tab.
 */
export function OverviewTab({ doc, pipelineDurationMs, onViewTraces }: OverviewTabProps) {
  const [showInternal, setShowInternal] = useState(false)

  const docR  = doc as Record<string, unknown>
  const meta  = ((doc.implicit_meta ?? {}) as Record<string, unknown>)
  const uMeta = ((doc.user_meta    ?? {}) as Record<string, unknown>)

  // Keys whose implicit_meta counterpart should be skipped (already shown elsewhere,
  // or are duplicates of a top-level doc field under a different name).
  const consumed = new Set([
    ...SKIP_IMPLICIT,
    // Identity — top-level fields that may be mirrored in implicit_meta
    'filename', 'format', 'extension', 'language', 'status',
    'file_size', 'id', 'collection_id', 'created_at',
    // Content — also covers common implicit_meta aliases (n_blocks ≠ block_count)
    'page_count', 'block_count', 'chunk_count', 'n_blocks',
    'n_figures', 'n_tables', 'has_scanned_pages',
    // Processing — top-level booleans + version
    'quality_score', 'pipeline_version', 'pipeline_duration_ms',
    'indexed', 'has_original', 'has_markdown', 'has_pdf',
    // Internal — shown explicitly in the Advanced section via lift()
    'source_hash',
  ])

  // Build a KVEntry from a label + value, return null when value is absent.
  const kv = (label: string, value: unknown): KVEntry | null =>
    value != null && value !== ''
      ? { key: label, value: <ValueRenderer value={value} /> }
      : null

  // Pull a field from top-level doc, falling back to implicit_meta, and mark consumed.
  function lift(key: string): unknown {
    consumed.add(key)
    return docR[key] !== undefined ? docR[key] : meta[key]
  }

  // ── Identity ──────────────────────────────────────────────────────────────
  const identityEntries = [
    kv('Filename',   doc.filename),
    kv('Format',     doc.format),
    kv('ID',         doc.id),
    kv('Collection', doc.collection_id),
    kv('Created',    doc.created_at),
    kv('Status',     doc.status),
    kv('Language',   doc.language),
    kv('File size',  doc.file_size != null ? formatFileSize(doc.file_size) : null),
  ].filter(Boolean) as KVEntry[]

  // ── Content & structure ───────────────────────────────────────────────────
  const contentEntries = [
    kv('Pages',         lift('page_count')),
    kv('Blocks',        lift('block_count')),
    kv('Chunks',        lift('chunk_count')),
    kv('Figures',       lift('n_figures')),
    kv('Tables',        lift('n_tables')),
    kv('Scanned pages', lift('has_scanned_pages')),
  ].filter(Boolean) as KVEntry[]

  // ── Processing (top-level fields) ─────────────────────────────────────────
  const processingBase: KVEntry[] = [
    kv('Quality score',     doc.quality_score != null ? doc.quality_score.toFixed(3) : null),
    kv('Pipeline version',  doc.pipeline_version),
    kv('Pipeline duration', pipelineDurationMs != null ? formatDuration(pipelineDurationMs) : null),
    kv('Indexed',           doc.indexed),
    kv('Original file',     doc.has_original),
    kv('Markdown export',   doc.has_markdown),
    kv('PDF export',        doc.has_pdf),
  ].filter(Boolean) as KVEntry[]

  // Drain remaining implicit_meta: route to Processing or Internal.
  const processingExtra: KVEntry[] = []
  const internalFromMeta: KVEntry[] = []

  for (const [k, v] of Object.entries(meta)) {
    if (consumed.has(k) || v == null) continue
    const val: ReactNode = k === 'budget_spent' && typeof v === 'number'
      ? <span style={{ fontSize: 11 }}>{formatBudget(v)}</span>
      : <ValueRenderer value={v} />
    const entry: KVEntry = { key: humanize(k), value: val }
    if (INTERNAL_IMPLICIT.has(k)) internalFromMeta.push(entry)
    else processingExtra.push(entry)
  }

  const processingEntries = [...processingBase, ...processingExtra]

  // ── User metadata ─────────────────────────────────────────────────────────
  const userEntries: KVEntry[] = Object.entries(uMeta)
    .filter(([, v]) => v != null)
    .map(([k, v]) => ({ key: humanize(k), value: <ValueRenderer value={v} /> }))

  // ── Internal (source hash + implicit_meta storage keys / fingerprints) ────
  // source_hash: try top-level first, fall back to implicit_meta (consumed above).
  const sourceHashVal = docR['source_hash'] ?? meta['source_hash']
  const internalEntries: KVEntry[] = [
    kv('Source hash', sourceHashVal),
    ...internalFromMeta,
  ].filter(Boolean) as KVEntry[]

  // ── Chain traces counts ───────────────────────────────────────────────────
  const parseCount = countArr(docR['chain_traces'])      || countArr(meta['chain_traces'])
  const embedCount = countArr(docR['embed_chain_traces']) || countArr(meta['embed_chain_traces'])
  const hasTraces  = parseCount > 0 || embedCount > 0

  const errors       = doc.pipeline_errors ?? []
  const staleReasons = doc.stale_reasons   ?? []
  const isStale      = doc.stale === true || staleReasons.length > 0

  // ── Render ────────────────────────────────────────────────────────────────
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>

      {isStale && (
        <div className="stale-banner">
          <div className="stale-banner-title">Stale — re-ingestion recommended</div>
          {staleReasons.length > 0
            ? <ul style={{ margin: 0, paddingLeft: 14 }}>
                {staleReasons.map((r, i) => <li key={i} className="stale-reason-item">{r}</li>)}
              </ul>
            : <span className="stale-reason-item">Pipeline version differs from current config.</span>
          }
        </div>
      )}

      {errors.length > 0 && (
        <div>
          <div className="stage-panel-label" style={{ marginBottom: 6 }}>
            Pipeline errors ({errors.length})
          </div>
          {errors.map((e, i) => (
            <div key={i} className="error-banner" style={{ marginBottom: 4, fontSize: 11 }}>{e}</div>
          ))}
        </div>
      )}

      <SectionBlock title="Identity"            entries={identityEntries} />
      <SectionBlock title="Content & structure" entries={contentEntries} />
      <SectionBlock title="Processing"          entries={processingEntries} />

      {userEntries.length > 0 && (
        <SectionBlock title="User metadata" entries={userEntries} />
      )}

      {internalEntries.length > 0 && (
        <SectionBlock
          title="Advanced"
          entries={showInternal ? internalEntries : []}
          action={
            <button
              type="button"
              className="overview-internal-btn"
              onClick={() => setShowInternal(s => !s)}
            >
              {showInternal ? '▲ hide' : '▼ show'} internal details
            </button>
          }
        />
      )}

      {hasTraces && (
        <div className="overview-section">
          <SectionHeader>Chain traces</SectionHeader>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginTop: 4 }}>
            <span className="text-dim" style={{ fontSize: 11 }}>
              {parseCount > 0 && `Parse: ${parseCount} trace${parseCount !== 1 ? 's' : ''}`}
              {parseCount > 0 && embedCount > 0 && ' · '}
              {embedCount > 0 && `Embed: ${embedCount} batch${embedCount !== 1 ? 'es' : ''}`}
            </span>
            {onViewTraces && (
              <button type="button" className="overview-traces-link" onClick={onViewTraces}>
                View in Chain traces tab →
              </button>
            )}
          </div>
        </div>
      )}

    </div>
  )
}
