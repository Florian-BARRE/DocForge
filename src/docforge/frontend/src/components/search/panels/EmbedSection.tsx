// ====== Code Summary ======
// EmbedSection — read-only information panel for the embed stage of the search
// pipeline. The embed provider is auto-derived from the ingestion config (S6) and
// cannot be changed here; this section renders that config via the ConfigTree helper.

// ====== Internal Project Imports ======
import type { ConfigState } from '../../../api/types'

// ── Component ─────────────────────────────────────────────────────────────────

/**
 * Read-only information panel for the embed stage.
 *
 * The embed provider is always auto-derived from the collection's ingestion
 * config and cannot be changed in the search context.
 *
 * Args:
 *   configState: Full collection config state (provides embedding_model and locality_policy).
 */
export function EmbedSection({ configState }: { configState: ConfigState | null }) {
  // Read from pipeline.embed — same source as S6 ingestion stage, avoids
  // divergence with the top-level embedding_model summary field.
  const embedCfg = (configState?.pipeline as Record<string, unknown> | undefined)?.embed

  return (
    <div>
      <div className="search-stage-description" style={{ marginBottom: 10 }}>
        Embed provider is derived from the ingestion config (S6) and cannot be changed here.
        Configure it from the Pipeline tab.
      </div>
      {embedCfg != null ? (
        <ConfigTree value={embedCfg} />
      ) : (
        <div className="stage-config-empty">No embed config found in pipeline.</div>
      )}
    </div>
  )
}

// ── ConfigTree ────────────────────────────────────────────────────────────────

/**
 * Recursively renders an arbitrary config object as indented key-value rows.
 *
 * Null / undefined values are shown as "—". Arrays are rendered inline as
 * comma-separated values unless their items are objects (in which case each
 * item is rendered as a nested block).
 *
 * Args:
 *   value:  The config object or scalar to render.
 *   depth:  Current indentation depth (used for nested objects).
 */
function ConfigTree({ value, depth = 0 }: { value: unknown; depth?: number }) {
  if (value === null || value === undefined) {
    return <span className="stage-panel-value" style={{ color: 'var(--text-dim)' }}>—</span>
  }

  if (typeof value !== 'object') {
    return <span className="stage-panel-value mono">{String(value)}</span>
  }

  if (Array.isArray(value)) {
    if (value.length === 0) return <span className="stage-panel-value" style={{ color: 'var(--text-dim)' }}>[]</span>
    // If items are primitives, render inline.
    if (value.every(v => typeof v !== 'object' || v === null)) {
      return <span className="stage-panel-value mono">{value.join(', ')}</span>
    }
    // Items are objects — render each as a numbered block.
    return (
      <div style={{ paddingLeft: depth > 0 ? 8 : 0 }}>
        {value.map((item, i) => (
          <div key={i} style={{ marginBottom: 4 }}>
            <span className="stage-panel-label" style={{ fontSize: 10, opacity: 0.7 }}>[{i}]</span>
            <ConfigTree value={item} depth={depth + 1} />
          </div>
        ))}
      </div>
    )
  }

  const entries = Object.entries(value as Record<string, unknown>).filter(([, v]) => v !== null && v !== undefined)
  return (
    <div style={{ paddingLeft: depth > 0 ? 12 : 0 }}>
      {entries.map(([k, v]) => (
        <div key={k} className="stage-panel-row" style={{ alignItems: 'flex-start', marginBottom: 2 }}>
          <span className="stage-panel-label mono" style={{ fontSize: 11 }}>{k}</span>
          {typeof v === 'object' && v !== null ? (
            <div style={{ flex: 1 }}>
              <ConfigTree value={v} depth={depth + 1} />
            </div>
          ) : (
            <span className="stage-panel-value mono">{String(v)}</span>
          )}
        </div>
      ))}
      {entries.length === 0 && (
        <div className="stage-config-empty" style={{ fontSize: 11 }}>Empty config.</div>
      )}
    </div>
  )
}
