// ====== Code Summary ======
// Pipeline inspector — full post-ingestion view for one document.  Layout:
//
//   ┌───────── Document header (filename + badges + actions) ────────────┐
//   ├───── Stage rail (left) ──────┼──── Active stage panel (right) ─────┤
//   │  Overview                    │                                     │
//   │  S0 · Ingest                 │  • Config used (resolved chain)     │
//   │  S1 · Parse                  │  • Chain traces (provider attempts) │
//   │  S2 · Enrich                 │  • Stats / artifacts                │
//   │  S4 · Chunk                  │  • Raw data via <ObjectTree>        │
//   │  S5 · Contextualize          │  • Stage-specific drill-down        │
//   │  S6 · Embed + Index          │                                     │
//   │  Raw IR                      │                                     │
//   │  Metadata                    │                                     │
//   └──────────────────────────────┴─────────────────────────────────────┘
//
// Every panel surfaces ALL fields available on `DocumentResponse` plus on-demand
// fetches (pages, chunks, presigned URLs).  Components are TS-typed against the
// auto-generated OpenAPI mirror — no shape is hand-maintained.

import { useState, useEffect, useRef, useCallback, useMemo } from 'react'
import type { Collection, Document } from '../../api/types'
import {
  getConfigState,
  getDocument,
  getDocumentOriginal,
  getDocumentMarkdown,
  getDocumentPdf,
  getBlockFigure,
  reingestDocument,
} from '../../api/client'
import { ChainTraceView } from './ChainTraceView'
import { ObjectTree } from '../ui/ObjectTree'
import { IRNavigator } from './IRNavigator'
import { ChunkBrowser } from './ChunkBrowser'
import { ContextualizePreview } from './ContextualizePreview'

interface Props {
  collection: Collection
  initialDoc: Document
  onBack: () => void
}

type StageKey =
  | 'overview' | 's0' | 's1' | 's2' | 's4' | 's5' | 's6'
  | 'ir' | 'meta'

interface StageDef {
  key: StageKey
  label: string
  shortLabel: string
  description: string
}

const STAGES: StageDef[] = [
  { key: 'overview', label: 'Overview',               shortLabel: 'Overview',    description: 'Document summary + ingestion lifecycle.' },
  { key: 's0',       label: 'S0 · Ingest',            shortLabel: 'S0',          description: 'Original file + Gotenberg conversion → PDF.' },
  { key: 's1',       label: 'S1 · Parse',             shortLabel: 'S1',          description: 'Parser chain → DocumentIR + figure crops.' },
  { key: 's2',       label: 'S2 · Enrich',            shortLabel: 'S2',          description: 'Per-figure classifier / OCR / VLM chains.' },
  { key: 's4',       label: 'S4 · Chunk',             shortLabel: 'S4',          description: 'Structure-aware chunking + intra-section split.' },
  { key: 's5',       label: 'S5 · Contextualize',     shortLabel: 'S5',          description: 'embed_text header (title + breadcrumb + body).' },
  { key: 's6',       label: 'S6 · Embed + Index',     shortLabel: 'S6',          description: 'Embed chain → Qdrant upsert (multi-vector hybrid).' },
  { key: 'ir',       label: 'Raw IR',                 shortLabel: 'IR',          description: 'Pages + per-block detail explorer.' },
  { key: 'meta',     label: 'Metadata',               shortLabel: 'Meta',        description: 'Implicit + user metadata, full document record.' },
]

export function PipelineInspector({ collection, initialDoc, onBack }: Props) {
  const [doc, setDoc] = useState<Document>(initialDoc)
  const [active, setActive] = useState<StageKey>('overview')
  const [downloading, setDownloading] = useState<string | null>(null)
  const [reingesting, setReingesting] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [markdownText, setMarkdownText] = useState<string | null>(null)
  const [markdownFigures, setMarkdownFigures] = useState<Record<string, string>>({})
  const [showMarkdown, setShowMarkdown] = useState(false)
  const [loadingMarkdown, setLoadingMarkdown] = useState(false)

  // Collection config-state lazy-fetched once so each panel can show the resolved
  // chain that produced this document (provider list, gate min_score, …).
  const [configState, setConfigState] = useState<Awaited<ReturnType<typeof getConfigState>> | null>(null)
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null)

  const stopPoll = useCallback(() => {
    if (pollRef.current) { clearInterval(pollRef.current); pollRef.current = null }
  }, [])

  // Sync with latest initialDoc when the parent swaps documents.
  useEffect(() => { setDoc(initialDoc) }, [initialDoc.id])

  // Auto-poll while pending/running.
  useEffect(() => {
    if (doc.status === 'running' || doc.status === 'pending') {
      stopPoll()
      pollRef.current = setInterval(async () => {
        try {
          const updated = await getDocument(collection.id, doc.id)
          setDoc(updated)
          if (updated.status !== 'running' && updated.status !== 'pending') stopPoll()
        } catch { /* keep polling */ }
      }, 2000)
    } else stopPoll()
    return stopPoll
  }, [doc.id, doc.status, collection.id, stopPoll])

  // Fetch collection config-state once per collection so panels can display the chain.
  useEffect(() => {
    let cancelled = false
    getConfigState(collection.id)
      .then(cfg => { if (!cancelled) setConfigState(cfg) })
      .catch(() => { /* non-critical */ })
    return () => { cancelled = true }
  }, [collection.id])

  // Markdown viewer + downloads + reingest — unchanged behaviour, kept compact.
  async function handleDownload(kind: 'original' | 'pdf' | 'markdown') {
    setDownloading(kind)
    setError(null)
    try {
      const r = kind === 'original'
        ? await getDocumentOriginal(collection.id, doc.id)
        : kind === 'pdf'
        ? await getDocumentPdf(collection.id, doc.id)
        : await getDocumentMarkdown(collection.id, doc.id)
      window.open(r.url, '_blank')
    } catch (err) { setError(String(err)) } finally { setDownloading(null) }
  }

  async function handleViewMarkdown() {
    if (showMarkdown) { setShowMarkdown(false); return }
    if (markdownText) { setShowMarkdown(true);  return }
    setLoadingMarkdown(true)
    setError(null)
    try {
      const { url } = await getDocumentMarkdown(collection.id, doc.id)
      const resp = await fetch(url)
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`)
      const text = await resp.text()
      setMarkdownText(text)
      const FIG_RE = /!\[fig:([^\]]+)\]\(fig:[^\)]+\)/g
      const blockIds = [...new Set([...text.matchAll(FIG_RE)].map(m => m[1] as string))]
      const urls: Record<string, string> = {}
      await Promise.allSettled(blockIds.map(async (blockId) => {
        try {
          const r = await getBlockFigure(collection.id, doc.id, blockId)
          urls[blockId] = r.url
        } catch { /* crop not ready */ }
      }))
      setMarkdownFigures(urls)
      setShowMarkdown(true)
    } catch (err) { setError(`Markdown viewer: ${String(err)}`) } finally { setLoadingMarkdown(false) }
  }

  async function handleReingest() {
    if (!confirm('Re-ingest this document? Existing chunks and index entries will be replaced.')) return
    setReingesting(true)
    setError(null)
    try {
      await reingestDocument(collection.id, doc.id, true)
      const updated = await getDocument(collection.id, doc.id)
      setDoc(updated)
    } catch (err) { setError(String(err)) } finally { setReingesting(false) }
  }

  // Resolved pipeline (per-stage subset of `configState.pipeline`).
  const pipeline = useMemo(
    () => (configState?.pipeline ?? {}) as Record<string, unknown>,
    [configState],
  )

  return (
    <div style={{ display: 'flex', flexDirection: 'column', flex: 1, overflow: 'hidden' }}>
      {/* ── Header ── */}
      <div className="inspector-header">
        <button type="button" className="btn btn-ghost" onClick={onBack} style={{ flexShrink: 0 }}>← Back</button>
        <div style={{ flex: 1, minWidth: 0 }}>
          <div className="inspector-filename">{doc.filename}</div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginTop: 4, flexWrap: 'wrap' }}>
            <StatusBadge status={doc.status} />
            {doc.page_count  != null && <span className="text-dim" style={{ fontSize: 11 }}>{doc.page_count} pp</span>}
            {doc.block_count != null && <span className="text-dim" style={{ fontSize: 11 }}>{doc.block_count} blocks</span>}
            {doc.chunk_count != null && <span className="text-dim" style={{ fontSize: 11 }}>{doc.chunk_count} chunks</span>}
            {doc.language               && <span className="text-dim" style={{ fontSize: 11 }}>{doc.language}</span>}
            {doc.quality_score != null && (
              <span className="tag" style={{
                fontSize: 10,
                color: doc.quality_score >= 0.5 ? 'var(--s-done)' : 'var(--s-running)',
                borderColor: 'var(--border)',
              }} title="Parser quality_score">
                q={doc.quality_score.toFixed(2)}
              </span>
            )}
          </div>
        </div>
        <div className="inspector-downloads">
          {doc.has_original && <SmallBtn loading={downloading === 'original'} onClick={() => void handleDownload('original')}>↓ Original</SmallBtn>}
          {doc.has_pdf      && <SmallBtn loading={downloading === 'pdf'}      onClick={() => void handleDownload('pdf')}>↓ PDF</SmallBtn>}
          {doc.has_markdown && (
            <>
              <SmallBtn loading={downloading === 'markdown'} onClick={() => void handleDownload('markdown')}>↓ IR .md</SmallBtn>
              <button
                type="button"
                className={`btn ${showMarkdown ? 'btn-primary' : 'btn-ghost'}`}
                style={{ fontSize: 11 }}
                disabled={loadingMarkdown}
                onClick={() => void handleViewMarkdown()}
              >
                {loadingMarkdown ? <span className="spin">⟳</span> : '◎'} {showMarkdown ? 'Hide IR' : 'View IR'}
              </button>
            </>
          )}
          <button type="button" className="btn" style={{ fontSize: 11 }} disabled={reingesting} onClick={handleReingest}>
            {reingesting ? <span className="spin">⟳</span> : '↺'} Re-ingest
          </button>
        </div>
      </div>

      {error && <div className="error-banner" style={{ margin: '8px 24px 0' }}>{error}</div>}

      {/* ── Inline markdown viewer ── */}
      {showMarkdown && markdownText && (
        <div className="markdown-viewer fadein">
          <div className="markdown-viewer-header">
            <span>IR Markdown — {doc.filename}</span>
            <span className="text-dim" style={{ fontSize: 10 }}>
              {Object.keys(markdownFigures).length > 0
                ? `${Object.keys(markdownFigures).length} figure(s) resolved`
                : ''}
            </span>
            <button type="button" className="btn-icon" onClick={() => setShowMarkdown(false)}>✕</button>
          </div>
          <div className="markdown-content">
            <MarkdownRenderer text={markdownText} figureUrls={markdownFigures} />
          </div>
        </div>
      )}

      {/* ── Body: stage rail + active panel ── */}
      <div className="inspector-body">
        <aside className="inspector-rail">
          {STAGES.map(s => (
            <button
              key={s.key}
              type="button"
              className={`inspector-rail-btn ${active === s.key ? 'inspector-rail-btn-active' : ''}`}
              onClick={() => setActive(s.key)}
              title={s.description}
            >
              <span className="inspector-rail-label">{s.label}</span>
              <StageHealth doc={doc} stage={s.key} />
            </button>
          ))}
        </aside>

        <main className="inspector-main">
          {active === 'overview'      && <OverviewPanel doc={doc} pipeline={pipeline} />}
          {active === 's0'            && <S0Panel doc={doc} />}
          {active === 's1'            && <S1Panel doc={doc} pipeline={pipeline} />}
          {active === 's2'            && <S2Panel doc={doc} pipeline={pipeline} />}
          {active === 's4'            && <S4Panel doc={doc} pipeline={pipeline} collectionId={collection.id} />}
          {active === 's5'            && <S5Panel doc={doc} pipeline={pipeline} collectionId={collection.id} />}
          {active === 's6'            && <S6Panel doc={doc} pipeline={pipeline} />}
          {active === 'ir'            && <IRNavigator doc={doc} collectionId={collection.id} />}
          {active === 'meta'          && <MetaPanel doc={doc} />}
        </main>
      </div>
    </div>
  )
}

// ── Stage health indicator ───────────────────────────────────────────────────

function StageHealth({ doc, stage }: { doc: Document; stage: StageKey }) {
  // Coarse heuristics: every stage is healthy when doc.status === 'done', running
  // while doc is pending/running.  S6 has its own `indexed` flag.
  let colour = 'var(--text-dim)'
  if (stage === 'overview') return null
  if (doc.status === 'running' || doc.status === 'pending') {
    colour = 'var(--s-running)'
  } else if (doc.status === 'error') {
    colour = 'var(--s-error)'
  } else if (stage === 's6') {
    colour = doc.indexed ? 'var(--s-done)' : 'var(--s-pending)'
  } else if (doc.status === 'done') {
    colour = 'var(--s-done)'
  }
  return <span className="inspector-rail-dot" style={{ background: colour }} />
}

// ── Panels ───────────────────────────────────────────────────────────────────

function OverviewPanel({ doc, pipeline }: { doc: Document; pipeline: Record<string, unknown> }) {
  const im = (doc.implicit_meta as Record<string, unknown>) ?? {}
  return (
    <div className="inspector-panel">
      <h3 className="panel-title">Overview</h3>
      <KvGrid rows={[
        ['Document ID', doc.id],
        ['Source hash', doc.source_hash],
        ['Status', doc.status],
        ['Format', doc.format],
        ['Pages', doc.page_count],
        ['Blocks', doc.block_count],
        ['Chunks', doc.chunk_count],
        ['Language', doc.language ?? '—'],
        ['Quality score', doc.quality_score?.toFixed(3) ?? '—'],
        ['Pipeline version', doc.pipeline_version],
        ['Indexed', doc.indexed ? 'yes' : 'no'],
        ['File size', fmtBytes(doc.file_size)],
        ['Created at', new Date(doc.created_at).toLocaleString()],
      ]} />

      {(doc.chain_traces?.length ?? 0) + (doc.embed_chain_traces?.length ?? 0) > 0 && (
        <Section title="Pipeline lineage">
          <ChainTraceView
            traces={[...(doc.chain_traces ?? []), ...(doc.embed_chain_traces ?? [])]}
            defaultOpenStages={['parse']}
            variant="detailed"
            label=""
          />
        </Section>
      )}

      <Section title="Resolved pipeline (collection)">
        <ObjectTree value={pipeline} label="pipeline" defaultDepth={1} />
      </Section>

      <Section title="Pipeline errors" hidden={(doc.pipeline_errors?.length ?? 0) === 0}>
        {(doc.pipeline_errors ?? []).map((e, i) => (
          <div key={i} className="error-banner" style={{ fontSize: 11 }}>{e}</div>
        ))}
      </Section>

      <Section title="Stage fingerprints" hidden={!im.s0_fingerprint && !im.s1_fingerprint && !im.s2_fingerprint}>
        <KvGrid rows={[
          ['s0_fingerprint', im.s0_fingerprint],
          ['s1_fingerprint', im.s1_fingerprint],
          ['s2_fingerprint', im.s2_fingerprint],
          ['ir_key', im.ir_key],
          ['markdown_key', im.markdown_key],
        ]} />
      </Section>
    </div>
  )
}

function S0Panel({ doc }: { doc: Document }) {
  const im = (doc.implicit_meta as Record<string, unknown>) ?? {}
  return (
    <div className="inspector-panel">
      <h3 className="panel-title">S0 · Ingest</h3>
      <p className="text-muted" style={{ fontSize: 12 }}>
        Original file content-addressed by blake3+sha256, optional Gotenberg conversion
        to PDF (office / web → PDF), uploaded to SeaweedFS under <code>original/&lt;hash&gt;</code>.
      </p>
      <KvGrid rows={[
        ['source_hash', doc.source_hash],
        ['file_size', fmtBytes(doc.file_size)],
        ['format', doc.format],
        ['has original blob', doc.has_original ? 'yes' : 'no'],
        ['has PDF blob', doc.has_pdf ? 'yes' : 'no'],
        ['converter_name', im.converter_name ?? '(not applicable)'],
        ['converter_version', im.converter_version],
      ]} />
      <Section title="Implicit metadata (S0 fields)">
        <ObjectTree value={im} label="implicit_meta" defaultDepth={1} alwaysCollapsedKeys={['chain_traces', 'embed_chain_traces']} />
      </Section>
    </div>
  )
}

function S1Panel({ doc, pipeline }: { doc: Document; pipeline: Record<string, unknown> }) {
  const parse = (pipeline.parse as Record<string, unknown> | undefined) ?? {}
  const parseTraces = (doc.chain_traces ?? []).filter(t => t.stage === 'parse')
  return (
    <div className="inspector-panel">
      <h3 className="panel-title">S1 · Parse</h3>
      <p className="text-muted" style={{ fontSize: 12 }}>
        Parser chain → DocumentIR.  Each provider produces an IR; the chain's gate
        escalates when quality_score falls below the threshold.
      </p>

      <Section title="Configured chain">
        <ObjectTree value={parse} label="parse" defaultDepth={2} />
      </Section>

      <Section title="Chain traces">
        {parseTraces.length > 0
          ? <ChainTraceView traces={parseTraces} variant="detailed" label="" defaultOpenStages={['parse']} />
          : <NoData label="No parse chain trace (chain didn't escalate)." />}
      </Section>

      <Section title="Stats">
        <KvGrid rows={[
          ['quality_score', doc.quality_score?.toFixed(3) ?? '—'],
          ['n_pages', doc.page_count],
          ['n_blocks', doc.block_count],
          ['language', doc.language ?? '—'],
        ]} />
      </Section>
    </div>
  )
}

function S2Panel({ doc, pipeline }: { doc: Document; pipeline: Record<string, unknown> }) {
  const enrich = (pipeline.enrich as Record<string, unknown> | undefined) ?? {}
  const im = (doc.implicit_meta as Record<string, unknown>) ?? {}
  return (
    <div className="inspector-panel">
      <h3 className="panel-title">S2 · Enrich</h3>
      <p className="text-muted" style={{ fontSize: 12 }}>
        Per-figure routing: <code>classifier → OCR → VLM</code>, each a chain.  Block-level
        chain traces live inside the figure blocks (visible under <strong>Raw IR</strong>).
      </p>

      <Section title="Classifier chain">
        <ObjectTree value={enrich.classifier_chain ?? []} label="classifier_chain" defaultDepth={2} />
        <KvGrid rows={[['classifier gate', JSON.stringify(enrich.classifier_gate ?? {})]]} />
      </Section>

      <Section title="OCR chain">
        <ObjectTree value={enrich.ocr_chain ?? []} label="ocr_chain" defaultDepth={2} />
        <KvGrid rows={[['ocr gate', JSON.stringify(enrich.ocr_gate ?? {})]]} />
      </Section>

      <Section title="VLM chain">
        <ObjectTree value={enrich.vlm_chain ?? []} label="vlm_chain" defaultDepth={2} />
        <KvGrid rows={[['vlm gate', JSON.stringify(enrich.vlm_gate ?? {})]]} />
      </Section>

      <Section title="Run stats">
        <KvGrid rows={[
          ['figures enriched', im.figures_enriched],
          // Counter pairs: (chain invocations) / (provider-call cache hits).
          // A hit means an identical crop was answered from cache — zero cost,
          // zero latency — typically a repeating logo or page header.
          ['Classifier — chain calls / cache hits',
            `${im.classifier_calls ?? 0} / ${im.classifier_cache_hits ?? 0}`],
          ['OCR — chain calls / cache hits',
            `${im.ocr_calls ?? 0} / ${im.ocr_cache_hits ?? 0}`],
          ['VLM — chain calls / cache hits',
            `${im.vlm_calls ?? 0} / ${im.vlm_cache_hits ?? 0}`],
          ['Chart-to-data extractions', im.chart_extractions],
          ['Budget spent (USD)', im.budget_spent],
          ['Max budget (config)', enrich.max_budget_usd],
          ['Chart-to-data enabled', String(enrich.chart_to_data ?? false)],
        ]} />
      </Section>
    </div>
  )
}

function S4Panel({ doc, pipeline, collectionId }: { doc: Document; pipeline: Record<string, unknown>; collectionId: string }) {
  const chunk = (pipeline.chunk as Record<string, unknown> | undefined) ?? {}
  return (
    <div className="inspector-panel">
      <h3 className="panel-title">S4 · Chunk</h3>
      <p className="text-muted" style={{ fontSize: 12 }}>
        Structure-aware chunking.  Heading skeleton (S1 + regex rules) drives section
        boundaries; <code>split_method</code> handles intra-section cuts when a section
        exceeds the token budget.
      </p>

      <Section title="Split method (resolved)">
        <ObjectTree value={chunk.split_method ?? {}} label="split_method" defaultDepth={2} />
      </Section>

      <Section title="Chunking flags">
        <KvGrid rows={[
          ['merge_short_sections', chunk.merge_short_sections],
          ['reinject_breadcrumb', chunk.reinject_breadcrumb],
          ['hierarchical', chunk.hierarchical],
          ['cross_references', chunk.cross_references],
        ]} />
      </Section>

      <Section title="Atomic policy">
        <ObjectTree value={chunk.atomic ?? {}} label="atomic" defaultDepth={1} />
      </Section>

      <Section title="Heading rules">
        <ObjectTree value={chunk.heading_rules ?? []} label="heading_rules" defaultDepth={0} alwaysCollapsedKeys={['heading_rules']} />
      </Section>

      <Section title="Chunks browser">
        <ChunkBrowser doc={doc} collectionId={collectionId} />
      </Section>
    </div>
  )
}

function S5Panel({ doc, pipeline, collectionId }: { doc: Document; pipeline: Record<string, unknown>; collectionId: string }) {
  const ctx = (pipeline.contextualize as Record<string, unknown> | undefined) ?? {}
  return (
    <div className="inspector-panel">
      <h3 className="panel-title">S5 · Contextualize</h3>
      <p className="text-muted" style={{ fontSize: 12 }}>
        Builds <code>embed_text</code> per chunk: optional document title + heading
        breadcrumb (configurable separator) + chunk body (separated by the configured
        header/body delimiter).
      </p>

      <Section title="Template configuration (persisted)">
        <KvGrid rows={[
          ['include_doc_title', String(ctx.include_doc_title ?? true)],
          ['include_breadcrumb', String(ctx.include_breadcrumb ?? true)],
          ['breadcrumb_separator', JSON.stringify(ctx.breadcrumb_separator ?? ' > ')],
          ['header_body_separator', JSON.stringify(ctx.header_body_separator ?? '\n\n')],
        ]} />
      </Section>

      <Section title="Template skeleton">
        <pre className="chunk-pre" style={{ fontSize: 11 }}>{previewTemplate(ctx)}</pre>
      </Section>

      <Section title="Live transformation preview">
        <ContextualizePreview doc={doc} collectionId={collectionId} config={ctx} />
      </Section>
    </div>
  )
}

function S6Panel({ doc, pipeline }: { doc: Document; pipeline: Record<string, unknown> }) {
  const embed = (pipeline.embed as Record<string, unknown> | undefined) ?? {}
  const embedTraces = doc.embed_chain_traces ?? []
  return (
    <div className="inspector-panel">
      <h3 className="panel-title">S6 · Embed + Index</h3>
      <p className="text-muted" style={{ fontSize: 12 }}>
        Embed chain → multi-vector Qdrant upsert.  Each batch produces one chain trace.
        Content vector + per-metadata-field named vectors (dense + sparse).
      </p>

      <Section title="Embed chain">
        <ObjectTree value={embed.chain ?? []} label="chain" defaultDepth={2} />
        <KvGrid rows={[['embed gate', JSON.stringify(embed.gate ?? {})]]} />
      </Section>

      <Section title="Chain traces (per batch)">
        {embedTraces.length > 0
          ? <ChainTraceView traces={embedTraces} variant="detailed" label="" defaultOpenStages={['embed']} />
          : <NoData label="No embed traces yet — document not indexed or chain unused." />}
      </Section>

      <Section title="Indexing status">
        <KvGrid rows={[
          ['Qdrant indexed', doc.indexed ? 'yes' : 'no'],
          ['Embedding model', (embed.chain as unknown[] | undefined)?.[0]
            ? JSON.stringify((embed.chain as Array<Record<string, unknown>>)[0]?.model)
            : '—'],
          ['Chunks indexed', doc.chunk_count],
        ]} />
      </Section>
    </div>
  )
}

function MetaPanel({ doc }: { doc: Document }) {
  return (
    <div className="inspector-panel">
      <h3 className="panel-title">Metadata</h3>
      <Section title="User metadata">
        <ObjectTree value={doc.user_meta} label="user_meta" defaultDepth={2} />
      </Section>
      <Section title="Implicit metadata">
        <ObjectTree value={doc.implicit_meta} label="implicit_meta" defaultDepth={1}
          alwaysCollapsedKeys={['chain_traces', 'embed_chain_traces']} />
      </Section>
      <Section title="Full document record">
        <ObjectTree value={doc as unknown} label="document" defaultDepth={0} />
      </Section>
    </div>
  )
}

// ── Reusable primitives ──────────────────────────────────────────────────────

function StatusBadge({ status }: { status: Document['status'] }) {
  const color =
    status === 'done'    ? 'var(--s-done)'    :
    status === 'error'   ? 'var(--s-error)'   :
    status === 'running' ? 'var(--s-running)' :
    'var(--text-dim)'
  return (
    <span className="tag" style={{ color, borderColor: color + '40', background: color + '10' }}>
      {status === 'running' && <span className="spin" style={{ fontSize: 9 }}>⟳</span>}
      {status}
    </span>
  )
}

function SmallBtn({ loading, onClick, children }: { loading: boolean; onClick: () => void; children: React.ReactNode }) {
  return (
    <button type="button" className="btn btn-ghost" style={{ fontSize: 11 }} disabled={loading} onClick={onClick}>
      {loading ? <span className="spin">⟳</span> : null} {children}
    </button>
  )
}

function Section({ title, children, hidden }: { title: string; children: React.ReactNode; hidden?: boolean }) {
  if (hidden) return null
  return (
    <div className="inspector-section">
      <div className="inspector-section-title">{title}</div>
      <div>{children}</div>
    </div>
  )
}

function KvGrid({ rows }: { rows: Array<[string, unknown]> }) {
  return (
    <div className="kv-grid">
      {rows.map(([k, v], i) => (
        <div key={i} className="kv-row">
          <span className="kv-k mono">{k}</span>
          <span className="kv-v mono">{v == null ? '—' : typeof v === 'object' ? JSON.stringify(v) : String(v)}</span>
        </div>
      ))}
    </div>
  )
}

function NoData({ label }: { label: string }) {
  return <div className="text-dim" style={{ fontSize: 11 }}>{label}</div>
}

// ── Helpers ─────────────────────────────────────────────────────────────────

function fmtBytes(n: number): string {
  if (n < 1024) return `${n} B`
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`
  return `${(n / 1024 / 1024).toFixed(1)} MB`
}

function previewTemplate(ctx: Record<string, unknown>): string {
  const include_doc_title = ctx.include_doc_title !== false
  const include_breadcrumb = ctx.include_breadcrumb !== false
  const sep = (ctx.breadcrumb_separator as string | undefined) ?? ' > '
  const bsep = (ctx.header_body_separator as string | undefined) ?? '\n\n'
  const parts: string[] = []
  if (include_doc_title) parts.push('<document title>')
  if (include_breadcrumb) parts.push('<H1>', '<H2>', '<H3>')
  const header = parts.join(sep)
  return `${header}${bsep}<chunk body>`
}

// ── Markdown renderer with inline figure images (unchanged) ──────────────────

const FIG_LINE_RE = /^!\[fig:([^\]]+)\]\(fig:[^\)]+\)$/

function MarkdownRenderer({ text, figureUrls }: { text: string; figureUrls: Record<string, string> }) {
  const lines = text.split('\n')
  return (
    <>
      {lines.map((line, i) => {
        const m = line.match(FIG_LINE_RE)
        if (m) {
          const blockId = m[1]
          const url = figureUrls[blockId]
          return url ? (
            <div key={i} className="ir-figure-wrap">
              <img src={url} alt={`fig:${blockId}`} className="ir-figure-img-inline" loading="lazy" />
              <span className="text-dim mono" style={{ fontSize: 9, display: 'block', marginTop: 2 }}>{blockId}</span>
            </div>
          ) : (
            <div key={i} className="ir-figure-placeholder">[figure: {blockId}]</div>
          )
        }
        return <div key={i} className="markdown-line">{line || ' '}</div>
      })}
    </>
  )
}
