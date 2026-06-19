// ====== Code Summary ======
// <ChainTraceView> — visual chain-of-fallbacks renderer.
//
// Each chain trace is drawn as a vertical flow:
//
//   ┌─────────────────────────────────────────┐
//   │ S1 · PARSE                              │
//   │ final: mineru · 2 attempts · 6.4s       │
//   ╰─┬───────────────────────────────────────╯
//     │
//   ┌─▼─[1/2]─────────────── ESCALATED ───────┐
//   │ docling                                 │
//   │ score ████░░░░░░ 0.42                   │
//   │ duration 2 340 ms                       │
//   ╰─────────────────────────────────────────╯
//        ↓
//     ESCALATED · score 0.42 below the gate
//        ↓
//   ┌─▼─[2/2]──────────────────── FINAL ──────┐
//   │ mineru                                  │
//   │ score ████████░░ 0.78                   │
//   │ duration 4 108 ms                       │
//   ╰─────────────────────────────────────────╯
//
// Each stage gets its own colour (parse=indigo, classifier=violet, ocr=amber,
// vlm=pink, embed=emerald) so multiple traces on the same panel stay visually
// distinct.  Used in the inspector "Pipeline lineage" panel and inline inside
// each figure block.

import type { ChainAttempt, ChainTrace } from '../../api/types'

interface Props {
  traces: ChainTrace[]
  defaultOpenStages?: string[]    // kept for API compat (unused in the new flow visual)
  label?: string
  variant?: 'compact' | 'detailed'
}

interface StageStyle {
  label: string
  colour: string      // base colour for borders / accents
  bg: string          // very light tint for backgrounds
  textOn: string      // tint suitable for foreground text
}

const STAGE_STYLES: Record<string, StageStyle> = {
  parse:      { label: 'S1 · Parse',      colour: '#6366f1', bg: 'rgba(99, 102, 241, 0.12)',  textOn: '#a5b4fc' },
  classifier: { label: 'S2 · Classifier', colour: '#a855f7', bg: 'rgba(168, 85, 247, 0.12)',  textOn: '#d8b4fe' },
  ocr:        { label: 'S2 · OCR',        colour: '#f59e0b', bg: 'rgba(245, 158, 11, 0.14)',  textOn: '#fcd34d' },
  vlm:        { label: 'S2 · VLM',        colour: '#ec4899', bg: 'rgba(236, 72, 153, 0.14)',  textOn: '#f9a8d4' },
  embed:      { label: 'S6 · Embed',      colour: '#10b981', bg: 'rgba(16, 185, 129, 0.14)',  textOn: '#6ee7b7' },
}

function styleFor(stage: string): StageStyle {
  return STAGE_STYLES[stage] ?? { label: stage, colour: '#94a3b8', bg: 'rgba(148, 163, 184, 0.12)', textOn: '#cbd5e1' }
}

export function ChainTraceView({ traces, label, variant = 'detailed' }: Props) {
  if (!traces || traces.length === 0) {
    if (variant === 'compact') return null
    return (
      <div className="picker" style={{ marginTop: 8 }}>
        <div className="picker-label">{label ?? 'Chain lineage'}</div>
        <div className="text-dim" style={{ fontSize: 11 }}>
          No chain trace recorded for this scope.
        </div>
      </div>
    )
  }

  return (
    <div className={`chain-flow chain-flow-${variant}`}>
      {variant === 'detailed' && label !== '' && (
        <div className="picker-label">{label ?? 'Chain lineage'}</div>
      )}
      <div className="chain-flow-stack">
        {traces.map((t, i) => <TraceFlow key={`${t.stage}-${i}`} trace={t} variant={variant} />)}
      </div>
    </div>
  )
}

// ── One trace → vertical flow of attempts ─────────────────────────────────

function TraceFlow({ trace, variant }: { trace: ChainTrace; variant: 'compact' | 'detailed' }) {
  const style = styleFor(trace.stage)
  const attempts = trace.attempts ?? []
  const totalDur = attempts.reduce((s, a) => s + a.duration_ms, 0)
  const finalIdx = attempts.findIndex(a => !a.escalated && a.succeeded)
  // Cache-hit shortcut: the chain was bypassed entirely because the same crop
  // bytes were already in the ProviderCallCache.  The synthetic trace carries
  // a single attempt with provider_id == "provider_cache" — render it as a
  // distinctive teal "CACHE HIT" card instead of the usual chain flow so the
  // operator can see at a glance how often dedup saved an API call.
  const isCacheHit =
    attempts.length === 1 && attempts[0].provider_id === 'provider_cache'

  if (isCacheHit) {
    return <CacheHitCard trace={trace} style={style} attempt={attempts[0]} />
  }

  return (
    <section
      className="chain-trace-card"
      style={{
        borderLeft: `3px solid ${style.colour}`,
        background: style.bg,
      }}
    >
      <header className="chain-trace-card-header">
        <span
          className="chain-trace-stage-pill"
          style={{ background: style.colour, color: '#fff' }}
        >
          {style.label}
        </span>
        <span className="chain-trace-summary">
          {trace.final_provider ? (
            <>
              <strong style={{ color: style.textOn }}>{trace.final_provider}</strong>
              <span className="text-dim"> · {attempts.length} attempt{attempts.length !== 1 ? 's' : ''} · {totalDur} ms</span>
            </>
          ) : (
            <span style={{ color: 'var(--s-error)' }}>
              ⚠ chain exhausted — {attempts.length} provider{attempts.length !== 1 ? 's' : ''} tried, none succeeded
            </span>
          )}
        </span>
      </header>

      {variant !== 'compact' && attempts.length > 0 && (
        <ol className="chain-flow-list">
          {attempts.map((a, i) => (
            <li key={i}>
              <AttemptCard
                style={style}
                attempt={a}
                idx={i}
                total={attempts.length}
                isFinal={i === finalIdx}
              />
              {i < attempts.length - 1 && (
                <EscalationArrow from={a} next={attempts[i + 1]} style={style} />
              )}
            </li>
          ))}
        </ol>
      )}
    </section>
  )
}

// ── One attempt card with score bar ───────────────────────────────────────

function AttemptCard({
  style, attempt, idx, total, isFinal,
}: {
  style: StageStyle
  attempt: ChainAttempt
  idx: number
  total: number
  isFinal: boolean
}) {
  // Status badge: green when this is the final accepted result, amber when
  // escalated, red when the call raised.
  let badge: { tag: string; bg: string; fg: string }
  if (!attempt.succeeded) {
    badge = { tag: 'FAIL', bg: 'rgba(239, 68, 68, 0.20)', fg: '#fecaca' }
  } else if (isFinal) {
    badge = { tag: 'FINAL', bg: 'rgba(34, 197, 94, 0.20)', fg: '#86efac' }
  } else {
    badge = { tag: 'ESCALATED', bg: 'rgba(245, 158, 11, 0.20)', fg: '#fcd34d' }
  }

  const score = attempt.score
  const scorePct = score != null ? Math.max(0, Math.min(1, score)) * 100 : 0

  return (
    <article
      className="chain-attempt"
      style={{
        borderColor: style.colour + '40',
        background: 'var(--panel-bg)',
      }}
    >
      <div className="chain-attempt-head">
        <span className="chain-attempt-index mono" style={{ color: style.textOn }}>
          {idx + 1}/{total}
        </span>
        <span className="chain-attempt-name mono">{attempt.provider_id}</span>
        <span className="chain-attempt-badge" style={{ background: badge.bg, color: badge.fg }}>
          {badge.tag}
        </span>
      </div>

      {/* Score bar — only when a score is known. */}
      {score != null && (
        <div className="chain-attempt-score">
          <div className="chain-attempt-bar">
            <div
              className="chain-attempt-bar-fill"
              style={{
                width: `${scorePct}%`,
                background: isFinal ? 'var(--s-done)' : (attempt.escalated ? 'var(--s-running)' : style.colour),
              }}
            />
          </div>
          <span className="chain-attempt-score-value mono">{score.toFixed(3)}</span>
        </div>
      )}
      {score == null && attempt.succeeded && (
        <div className="text-dim chain-attempt-meta">score unknown (provider did not advertise one)</div>
      )}

      <div className="chain-attempt-meta">
        <span className="text-dim">⏱ {attempt.duration_ms} ms</span>
        {attempt.cost_usd > 0 && (
          <span className="text-dim">· ${attempt.cost_usd.toFixed(4)}</span>
        )}
        {attempt.error && (
          <span className="chain-attempt-error" title={attempt.error}>
            ⚠ {attempt.error}
          </span>
        )}
      </div>
    </article>
  )
}

// ── Cache-hit card (degenerate trace where the chain didn't run) ──────────

function CacheHitCard({
  trace, style, attempt,
}: {
  trace: ChainTrace
  style: StageStyle
  attempt: ChainAttempt
}) {
  // Teal accent — distinct from every stage colour — to signal "this didn't
  // run, it was answered from cache".  The original provider id is embedded
  // in attempt.error ("cache hit — would have called X").
  const CACHE = '#14b8a6'
  return (
    <section
      className="chain-trace-card"
      style={{
        borderLeft: `3px solid ${CACHE}`,
        background: 'rgba(20, 184, 166, 0.10)',
      }}
    >
      <header className="chain-trace-card-header">
        <span
          className="chain-trace-stage-pill"
          style={{ background: style.colour, color: '#fff' }}
        >
          {style.label}
        </span>
        <span
          className="chain-trace-stage-pill"
          style={{ background: CACHE, color: '#fff', marginLeft: 6 }}
          title="Result served from the provider-call cache — the chain did not run."
        >
          ⚡ CACHE HIT
        </span>
        <span className="chain-trace-summary text-dim">
          {attempt.error ?? 'identical crop already processed earlier — 0 ms, 0 USD'}
        </span>
      </header>
    </section>
  )
}

// ── Escalation arrow between two attempts ─────────────────────────────────

function EscalationArrow({
  from, next, style,
}: {
  from: ChainAttempt
  next: ChainAttempt
  style: StageStyle
}) {
  // Reason inferred from the previous attempt's status.
  let reason: string
  if (!from.succeeded) {
    reason = 'provider raised — falling back to the next'
  } else if (from.score != null) {
    reason = `score ${from.score.toFixed(3)} below the gate threshold → escalate`
  } else {
    reason = 'gate decided to escalate'
  }

  return (
    <div className="chain-arrow" style={{ color: style.textOn }}>
      <span className="chain-arrow-stem" style={{ background: style.colour }} />
      <span className="chain-arrow-label">
        ↓ ESCALATE · {reason}
        <span className="text-dim"> · next: {next.provider_id}</span>
      </span>
    </div>
  )
}
