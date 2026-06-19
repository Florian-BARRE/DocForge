// ====== Code Summary ======
// <ContextualizePreview> — visual S5 transformation diff for a single chunk.
// Shows three columns side by side so you can see exactly what S5 prepended:
//
//   [ raw_text only ] → [ + document title ] → [ + breadcrumb = embed_text ]
//
// The user picks any chunk from the document; the preview re-runs entirely from
// chunk.prov.heading_path + chunk.raw_text + the live ContextualizeConfig that
// produced this collection's chunks.

import { useEffect, useMemo, useState } from 'react'
import type { ChunkResponse, Document } from '../../api/types'
import { listChunks } from '../../api/client'

interface Props {
  doc: Document
  collectionId: string
  config: Record<string, unknown>   // pipeline.contextualize
}

export function ContextualizePreview({ doc, collectionId, config }: Props) {
  const [chunks, setChunks] = useState<ChunkResponse[]>([])
  const [loading, setLoading] = useState(false)
  const [selectedIdx, setSelectedIdx] = useState(0)

  // The preview reflects exactly the persisted ContextualizeConfig (no live knobs).
  // Editing happens in the Config tab; this panel is read-only by design.
  const includeDocTitle    = config.include_doc_title !== false
  const includeBreadcrumb  = config.include_breadcrumb !== false
  const breadcrumbSep      = (config.breadcrumb_separator as string | undefined) ?? ' > '
  const bodySep            = (config.header_body_separator as string | undefined) ?? '\n\n'

  useEffect(() => {
    if (doc.status !== 'done') return
    let cancelled = false
    setLoading(true)
    listChunks(collectionId, doc.id, { limit: 200 })
      .then(res => { if (!cancelled) setChunks(res.chunks) })
      .catch(() => { /* non-critical */ })
      .finally(() => { if (!cancelled) setLoading(false) })
    return () => { cancelled = true }
  }, [doc.id, doc.status, collectionId])

  const chunk = chunks[selectedIdx]
  const docTitle = (doc as unknown as { title?: string }).title ?? doc.filename.replace(/\.[^/.]+$/, '')

  // ── Render the three transformation steps ─────────────────────────────────
  const breadcrumb = useMemo(() => {
    if (!chunk) return ''
    const prov = chunk.prov as Record<string, unknown> | undefined
    return typeof prov?.heading_path === 'string' ? prov.heading_path : ''
  }, [chunk])

  const steps = useMemo(() => {
    if (!chunk) return null
    const body = chunk.raw_text
    // Step 1 : raw body only.
    const step1 = body
    // Step 2 : +document title (only when not already in the breadcrumb).
    const firstCrumb = breadcrumb.split(breadcrumbSep, 1)[0] ?? ''
    const titleOnIts = includeDocTitle && docTitle && docTitle !== firstCrumb
    const step2 = titleOnIts ? `${docTitle}${bodySep}${body}` : step1
    // Step 3 : +breadcrumb.  The S5 logic joins title + breadcrumb segments with the same sep.
    const segments: string[] = []
    if (titleOnIts) segments.push(docTitle)
    if (includeBreadcrumb && breadcrumb) segments.push(breadcrumb)
    const header = segments.join(breadcrumbSep)
    const step3 = header ? `${header}${bodySep}${body}` : body
    return { step1, step2, step3 }
  }, [chunk, docTitle, breadcrumb, includeDocTitle, includeBreadcrumb, breadcrumbSep, bodySep])

  if (doc.status !== 'done') {
    return (
      <div className="text-muted" style={{ fontSize: 12, padding: 12 }}>
        Pipeline not done — no chunks to preview.
      </div>
    )
  }
  if (loading) return <div className="text-muted" style={{ padding: 12 }}><span className="spin">⟳</span> Loading chunks…</div>
  if (chunks.length === 0) return <div className="text-dim" style={{ padding: 12 }}>No chunks found.</div>

  return (
    <div className="ctx-preview">
      {/* ── Chunk picker ── */}
      <div className="ctx-preview-picker">
        <button
          type="button"
          className="btn btn-ghost"
          disabled={selectedIdx === 0}
          onClick={() => setSelectedIdx(i => Math.max(0, i - 1))}
          style={{ fontSize: 11 }}
        >← prev</button>
        <select
          className="input select"
          value={selectedIdx}
          onChange={e => setSelectedIdx(parseInt(e.target.value, 10))}
          style={{ flex: 1, fontSize: 11 }}
        >
          {chunks.map((c, i) => (
            <option key={c.id} value={i}>
              #{i + 1} · {c.strategy} · {c.token_count} tok · {c.raw_text.slice(0, 60)}…
            </option>
          ))}
        </select>
        <button
          type="button"
          className="btn btn-ghost"
          disabled={selectedIdx === chunks.length - 1}
          onClick={() => setSelectedIdx(i => Math.min(chunks.length - 1, i + 1))}
          style={{ fontSize: 11 }}
        >next →</button>
      </div>

      {/* ── Three-column diff ── */}
      {steps && (
        <div className="ctx-preview-cols">
          <Col title="Raw text (S4 chunk body)" body={steps.step1} />
          <Col title={includeDocTitle ? '+ document title' : '(title disabled)'} body={steps.step2} highlight={includeDocTitle && docTitle ? docTitle : null} />
          <Col title="= embed_text (sent to S6)" body={steps.step3} highlight={includeBreadcrumb && breadcrumb ? breadcrumb : null} highlight2={includeDocTitle && docTitle ? docTitle : null} />
        </div>
      )}

      {chunk && (
        <div style={{ fontSize: 10, marginTop: 8 }} className="text-dim">
          chunk.id <span className="mono">{chunk.id}</span> · {chunk.token_count} tokens ·
          {chunk.strategy} · pages {(chunk.prov as Record<string, unknown>)?.pages
            ? (((chunk.prov as Record<string, unknown>).pages) as number[]).join(',')
            : '—'}
        </div>
      )}
    </div>
  )
}

function Col({ title, body, highlight, highlight2 }: { title: string; body: string; highlight?: string | null; highlight2?: string | null }) {
  // Wrap any occurrence of `highlight` and `highlight2` in coloured spans so the
  // reader sees exactly which substring S5 added.  Order: title first, breadcrumb after.
  const rendered = useMemo(() => {
    let out: React.ReactNode[] = [body]
    if (highlight2) out = wrap(out, highlight2, 'ctx-preview-mark-title')
    if (highlight)  out = wrap(out, highlight,  'ctx-preview-mark-breadcrumb')
    return out
  }, [body, highlight, highlight2])

  return (
    <div className="ctx-preview-col">
      <div className="ctx-preview-col-title">{title}</div>
      <pre className="ctx-preview-pre">{rendered}</pre>
    </div>
  )
}

// Recursively wrap occurrences of `needle` inside an array of React nodes.
function wrap(parts: React.ReactNode[], needle: string, cls: string): React.ReactNode[] {
  if (!needle) return parts
  return parts.flatMap((p, i) => {
    if (typeof p !== 'string') return [p]
    const idx = p.indexOf(needle)
    if (idx < 0) return [p]
    return [
      p.slice(0, idx),
      <span key={`${i}-${cls}`} className={cls}>{needle}</span>,
      ...wrap([p.slice(idx + needle.length)], needle, cls),
    ]
  })
}
