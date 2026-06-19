// ====== Code Summary ======
// Step 2 of Inspect mode — shows and edits the pipeline config for the selected collection.
//
// Driven entirely by /api/v1/discovery:
//   • `patch.pipeline.*` overlays → grouped per stage segment (parse / enrich / chunk / embed)
//     and rendered via <ChoicePicker> (picker overlays + scalar overlays).
//   • The non-pipeline body fields of `ConfigUpdateRequest` (note, …) are rendered via the
//     generic <RequestForm> so any new field added server-side appears automatically.
//
// Stage names and the dynamic-field set are derived from discovery — no hardcoded list.

import { useState, useEffect } from 'react'
import type {
  Collection, ConfigHistoryResponse, ConfigState, DiscoveryResponse,
} from '../../api/types'
import {
  getConfigState, getConfigHistory, getDiscovery, updateConfig, rollbackConfig,
} from '../../api/client'
import { RequestForm } from '../ui/RequestForm'
import { DynamicFieldsGroup } from '../ui/DynamicFieldsGroup'

interface Props {
  collection: Collection
  onConfigSaved?: (state: ConfigState) => void
}

// Stage segment → human label (presentation only; the set itself comes from discovery).
const STAGE_LABELS: Record<string, string> = {
  parse: 'S1 · Parse',
  enrich: 'S2 · Enrich',
  chunk: 'S4 · Chunk',
  embed: 'S6 · Embed',
}
const STAGE_ORDER = ['parse', 'enrich', 'chunk', 'embed']

export function ConfigStep({ collection, onConfigSaved }: Props) {
  const [configState, setConfigState] = useState<ConfigState | null>(null)
  const [discovery, setDiscovery] = useState<DiscoveryResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [pipelinePatch, setPipelinePatch] = useState<Record<string, unknown>>({})
  const [bodyPatch, setBodyPatch] = useState<Record<string, unknown>>({})
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [history, setHistory] = useState<ConfigHistoryResponse | null>(null)
  const [historyLoading, setHistoryLoading] = useState(false)
  const [showHistory, setShowHistory] = useState(false)

  // 1. Load config state + scoped discovery on mount or collection change.
  useEffect(() => {
    void loadAll()
  }, [collection.id])

  async function loadAll() {
    setLoading(true)
    setError(null)
    try {
      const [cfg, disc] = await Promise.all([
        getConfigState(collection.id),
        getDiscovery(collection.id),
      ])
      setConfigState(cfg)
      setPipelinePatch((cfg.pipeline as Record<string, unknown>) ?? {})
      setBodyPatch({})
      setDiscovery(disc)
    } catch (err) {
      setError(String(err))
    } finally {
      setLoading(false)
    }
  }

  // 2. Locate the update_config endpoint — pipeline overlays will be rendered by
  // <DynamicFieldsGroup prefix="patch.pipeline"> below.
  const updateEndpoint = discovery?.endpoints.find(e => e.route_name === 'update_config')
  const hasFields = !!updateEndpoint && (updateEndpoint.dynamic_fields ?? [])
    .some(df => df.field_path.startsWith('patch.pipeline.'))

  // 4. Save config.
  async function save() {
    setSaving(true)
    setError(null)
    try {
      const result = await updateConfig(
        collection.id,
        { pipeline: pipelinePatch },
        typeof bodyPatch.note === 'string' ? (bodyPatch.note as string) : undefined,
      )
      setConfigState(result)
      setPipelinePatch((result.pipeline as Record<string, unknown>) ?? {})
      setBodyPatch({})
      setSaved(true)
      onConfigSaved?.(result)
    } catch (err) {
      setError(String(err))
    } finally {
      setSaving(false)
    }
  }

  // 5. History helpers.
  async function loadHistory() {
    setHistoryLoading(true)
    try {
      setHistory(await getConfigHistory(collection.id))
    } catch { /* non-critical */ }
    finally { setHistoryLoading(false) }
  }

  function toggleHistory() {
    if (!showHistory && !history) void loadHistory()
    setShowHistory(v => !v)
  }

  async function handleRollback(version: number) {
    if (!confirm(`Roll back to version ${version}?`)) return
    setSaving(true)
    setError(null)
    try {
      const result = await rollbackConfig(collection.id, version)
      setConfigState(result)
      setPipelinePatch((result.pipeline as Record<string, unknown>) ?? {})
      setSaved(true)
      await loadHistory()
    } catch (err) {
      setError(String(err))
    } finally {
      setSaving(false)
    }
  }

  if (loading) {
    return (
      <div className="panel">
        <div className="text-muted"><span className="spin">⟳</span> Loading config…</div>
      </div>
    )
  }

  return (
    <div className="panel fadein">
      <div className="panel-header">
        <div className="panel-title">Pipeline configuration</div>
        <div className="panel-meta text-muted">
          {configState && (
            <>
              <span className="mono">{configState.pipeline_version}</span>
              {configState.needs_reindex && (
                <span className="tag tag-running" style={{ marginLeft: 8 }}>reindex needed</span>
              )}
            </>
          )}
        </div>
      </div>

      {error && <div className="error-banner">{error}</div>}

      {!hasFields && !loading && (
        <div className="empty" style={{ padding: '32px 0' }}>
          <div className="text-muted">
            {discovery ? 'No configurable pipeline stages found.' : 'Discovery not available.'}
          </div>
        </div>
      )}

      {updateEndpoint && (
        <DynamicFieldsGroup
          fields={updateEndpoint.dynamic_fields ?? []}
          prefix="patch.pipeline"
          value={pipelinePatch}
          onChange={v => { setPipelinePatch(v); setSaved(false) }}
          groupLabels={STAGE_LABELS}
          groupOrder={STAGE_ORDER}
          discovery={discovery ?? undefined}
        />
      )}

      {/* Non-pipeline body fields (note, …) — generic via RequestForm */}
      {updateEndpoint && discovery && (
        <RequestForm
          endpoint={updateEndpoint}
          discovery={discovery}
          body={bodyPatch}
          query={{}}
          onBodyChange={setBodyPatch}
          onQueryChange={() => {}}
          excludeBodyFields={['patch']}
        />
      )}

      {hasFields && (
        <div className="row-end" style={{ marginTop: 20 }}>
          {error && <span style={{ color: 'var(--s-error)', flex: 1, fontSize: 12 }}>{error}</span>}
          {saved && !error && <span className="text-muted">Saved.</span>}
          <button
            type="button"
            className="btn btn-ghost"
            onClick={() => {
              if (configState) {
                setPipelinePatch((configState.pipeline as Record<string, unknown>) ?? {})
                setBodyPatch({})
              }
            }}
          >
            Reset
          </button>
          <button
            type="button"
            className="btn btn-primary"
            onClick={save}
            disabled={saving}
          >
            {saving ? <span className="spin">⟳</span> : null}
            {saving ? ' Saving…' : 'Save config'}
          </button>
        </div>
      )}

      {/* Config history */}
      <div className="history-section">
        <button type="button" className="btn btn-ghost" style={{ fontSize: 11 }} onClick={toggleHistory}>
          {showHistory ? '▲' : '▼'} Config history {history ? `(${history.total})` : ''}
        </button>
        {showHistory && (
          <div className="history-list fadein">
            {historyLoading && <div className="text-muted" style={{ padding: '8px 10px' }}>Loading…</div>}
            {history?.versions.map(v => (
              <div key={v.version} className="history-row">
                <span className="history-version mono">v{v.version}</span>
                <span className="history-pv mono text-muted">{v.pipeline_version}</span>
                <span className="history-note text-dim">{v.note ?? '—'}</span>
                <span className="history-date text-dim">{new Date(v.created_at).toLocaleString()}</span>
                <button
                  type="button"
                  className="btn-icon"
                  title={`Roll back to v${v.version}`}
                  disabled={saving}
                  onClick={() => void handleRollback(v.version)}
                >↩</button>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Config transparency (warnings / defaulted / notes) */}
      {configState?.applied && (
        <details className="applied-envelope" style={{ marginTop: 16 }}>
          <summary className="text-muted" style={{ fontSize: 11, cursor: 'pointer' }}>
            Config transparency ▾
          </summary>
          <div className="applied-body">
            {(configState.applied.warnings?.length ?? 0) > 0 && (
              <div>
                <span className="tag tag-running">warnings</span>
                {(configState.applied.warnings ?? []).map((w, i) => (
                  <div key={i} className="applied-item text-muted">{w.field}: {w.message}</div>
                ))}
              </div>
            )}
            {(configState.applied.defaulted?.length ?? 0) > 0 && (
              <div>
                <span className="text-dim" style={{ fontSize: 11 }}>defaulted: </span>
                <span className="mono text-muted" style={{ fontSize: 11 }}>
                  {(configState.applied.defaulted ?? []).join(', ')}
                </span>
              </div>
            )}
            {configState.applied.notes?.map((n, i) => (
              <div key={i} className="applied-item text-dim" style={{ fontSize: 11 }}>{n}</div>
            ))}
          </div>
        </details>
      )}
    </div>
  )
}
