// ====== Code Summary ======
// Search pipeline configuration panel — query transform strategy picker
// (rewrite / HyDE / multi-query) and reranker toggle, dynamically built from
// the collection's stored pipeline.search config.  Changes auto-save via updateConfig.

import { useCallback, useEffect, useRef, useState } from 'react'
import { updateConfig } from '../../api/client'

// ── Types ────────────────────────────────────────────────────────────────────

export interface QueryTransformCfg {
  strategy: 'none' | 'rewrite' | 'hyde' | 'multi_query'
  n_variants: number
  llm: { id: string; [key: string]: unknown } | null
}

export interface RerankCfg {
  enabled: boolean
  candidate_k: number
  top_n: number
  chain: { id: string; [key: string]: unknown }[]
}

export interface SearchPipelineCfg {
  query_transform: QueryTransformCfg
  rerank: RerankCfg
}

export const DEFAULT_SEARCH_PIPELINE: SearchPipelineCfg = {
  query_transform: { strategy: 'none', n_variants: 3, llm: null },
  rerank: { enabled: false, candidate_k: 50, top_n: 10, chain: [] },
}

// ── Static metadata ──────────────────────────────────────────────────────────

const STRATEGIES: { id: QueryTransformCfg['strategy']; label: string; hint: string }[] = [
  { id: 'none',        label: 'None',        hint: 'Pass query through unchanged (default)' },
  { id: 'rewrite',     label: 'Rewrite',     hint: 'LLM cleans and expands the query before retrieval' },
  { id: 'hyde',        label: 'HyDE',        hint: 'Generate a hypothetical answer and embed it — good for factoid queries' },
  { id: 'multi_query', label: 'Multi-Query', hint: 'Generate N query variants and fuse results with RRF' },
]

const LLM_PROVIDERS: { id: string; label: string; hint: string }[] = [
  { id: 'local_llm',  label: 'Local',  hint: 'Any OpenAI-compat endpoint — reads LLM_API_BASE_URL from env' },
  { id: 'openai_llm', label: 'OpenAI', hint: 'Cloud OpenAI API — reads OPENAI_API_KEY from env' },
]

const RERANKERS: { id: string; label: string; hint: string }[] = [
  { id: 'bge_reranker',  label: 'BGE-Reranker', hint: 'Local · BAAI/bge-reranker-v2-m3 via TEI (BGE_RERANKER_URL)' },
  { id: 'cohere_rerank', label: 'Cohere',        hint: 'Cloud · Cohere Rerank v3.5 (COHERE_API_KEY)' },
]

// ── Component ────────────────────────────────────────────────────────────────

interface Props {
  collectionId: string
  initialConfig: SearchPipelineCfg
  onConfigChange?: (cfg: SearchPipelineCfg) => void
}

/**
 * Search pipeline configuration panel.
 *
 * Renders query transform strategy chips and a reranker toggle, each section
 * derived from the collection's stored pipeline.search config.  Changes are
 * debounced and persisted automatically via the config/update endpoint.
 *
 * Props:
 *   collectionId: Target collection (used for saving).
 *   initialConfig: Current pipeline.search config loaded by the parent.
 *   onConfigChange: Fired on every local state change (before save) so the
 *     parent can update its own copy (e.g. to show pipeline badges).
 */
export function SearchPipelinePanel({ collectionId, initialConfig, onConfigChange }: Props) {
  const [cfg, setCfg] = useState<SearchPipelineCfg>(initialConfig)
  const [saveState, setSaveState] = useState<'idle' | 'saving' | 'saved' | 'error'>('idle')
  const saveTimer = useRef<ReturnType<typeof setTimeout> | null>(null)
  // Track whether this is the first render after an initialConfig load so we
  // don't immediately re-save the config we just received from the server.
  const skipNextSave = useRef(true)

  // Re-sync local state when parent loads a different collection.
  useEffect(() => {
    setCfg(initialConfig)
    setSaveState('idle')
    skipNextSave.current = true
  }, [initialConfig])

  // Debounced auto-save: fires 600 ms after the last user change.
  const scheduleSave = useCallback((newCfg: SearchPipelineCfg) => {
    if (saveTimer.current) clearTimeout(saveTimer.current)
    setSaveState('saving')
    saveTimer.current = setTimeout(async () => {
      try {
        await updateConfig(
          collectionId,
          { pipeline: { search: newCfg } },
          'Updated search pipeline config',
        )
        setSaveState('saved')
        setTimeout(() => setSaveState('idle'), 1500)
      } catch {
        setSaveState('error')
        setTimeout(() => setSaveState('idle'), 3000)
      }
    }, 600)
  }, [collectionId])

  function applyChange(newCfg: SearchPipelineCfg) {
    setCfg(newCfg)
    onConfigChange?.(newCfg)
    if (skipNextSave.current) {
      skipNextSave.current = false
      return
    }
    scheduleSave(newCfg)
  }

  // ── Mutators ────────────────────────────────────────────────────────────────

  function setStrategy(strategy: QueryTransformCfg['strategy']) {
    const llm = strategy !== 'none'
      ? (cfg.query_transform.llm ?? { id: 'local_llm' })
      : null
    applyChange({ ...cfg, query_transform: { ...cfg.query_transform, strategy, llm } })
  }

  function setNVariants(n: number) {
    applyChange({ ...cfg, query_transform: { ...cfg.query_transform, n_variants: n } })
  }

  function setLlmProvider(id: string) {
    applyChange({ ...cfg, query_transform: { ...cfg.query_transform, llm: { id } } })
  }

  function setRerankEnabled(enabled: boolean) {
    // Default to BGE reranker when the user enables reranking for the first time.
    const chain = enabled && cfg.rerank.chain.length === 0 ? [{ id: 'bge_reranker' }] : cfg.rerank.chain
    applyChange({ ...cfg, rerank: { ...cfg.rerank, enabled, chain } })
  }

  function setRerankProvider(id: string) {
    applyChange({ ...cfg, rerank: { ...cfg.rerank, chain: [{ id }] } })
  }

  function setRerankInt(key: 'candidate_k' | 'top_n', raw: string) {
    const val = parseInt(raw) || (key === 'candidate_k' ? 50 : 10)
    applyChange({ ...cfg, rerank: { ...cfg.rerank, [key]: val } })
  }

  const activeReranker = cfg.rerank.chain[0]?.id ?? 'bge_reranker'
  const activeLlm = cfg.query_transform.llm?.id ?? 'local_llm'

  return (
    <div className="search-pipeline-panel">

      {/* ── Panel header ── */}
      <div className="search-params-title" style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        <span>Search Pipeline</span>
        <SaveIndicator state={saveState} />
      </div>

      {/* ── Query Transform ── */}
      <div className="pipeline-section">
        <div className="pipeline-section-label">Query Transform</div>
        <div className="pipeline-chips">
          {STRATEGIES.map(s => (
            <button
              key={s.id}
              type="button"
              className={`pipeline-chip${cfg.query_transform.strategy === s.id ? ' pipeline-chip-active' : ''}`}
              title={s.hint}
              onClick={() => setStrategy(s.id)}
            >
              {s.label}
            </button>
          ))}
        </div>

        {/* multi_query: n_variants slider */}
        {cfg.query_transform.strategy === 'multi_query' && (
          <div className="pipeline-sub-row">
            <span className="pipeline-sub-label">Variants</span>
            <div className="weight-slider-wrap" style={{ flex: 1, maxWidth: 180 }}>
              <input
                type="range" min={2} max={6} step={1}
                value={cfg.query_transform.n_variants}
                className="weight-slider"
                style={{ '--thumb-color': 'var(--accent)' } as React.CSSProperties}
                onChange={e => setNVariants(parseInt(e.target.value))}
              />
            </div>
            <span className="mono" style={{ fontSize: 11, color: 'var(--accent)', minWidth: 14 }}>
              {cfg.query_transform.n_variants}
            </span>
          </div>
        )}

        {/* LLM provider picker when transform is active */}
        {cfg.query_transform.strategy !== 'none' && (
          <div className="pipeline-sub-row">
            <span className="pipeline-sub-label">LLM</span>
            <div className="pipeline-chips" style={{ marginBottom: 0 }}>
              {LLM_PROVIDERS.map(p => (
                <button
                  key={p.id}
                  type="button"
                  className={`pipeline-chip pipeline-chip-sm${activeLlm === p.id ? ' pipeline-chip-active' : ''}`}
                  title={p.hint}
                  onClick={() => setLlmProvider(p.id)}
                >
                  {p.label}
                </button>
              ))}
            </div>
          </div>
        )}
      </div>

      {/* ── Reranker ── */}
      <div className="pipeline-section" style={{ marginBottom: 0 }}>
        <div className="pipeline-section-label" style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <span>Reranker</span>
          <button
            type="button"
            className={`toggle${cfg.rerank.enabled ? ' toggle-on' : ''}`}
            onClick={() => setRerankEnabled(!cfg.rerank.enabled)}
            title={cfg.rerank.enabled ? 'Disable reranking' : 'Enable reranking'}
          >
            <span className="toggle-thumb" />
          </button>
        </div>

        {cfg.rerank.enabled && (
          <div style={{ marginTop: 8 }}>
            <div className="pipeline-chips">
              {RERANKERS.map(r => (
                <button
                  key={r.id}
                  type="button"
                  className={`pipeline-chip${activeReranker === r.id ? ' pipeline-chip-active' : ''}`}
                  title={r.hint}
                  onClick={() => setRerankProvider(r.id)}
                >
                  {r.label}
                </button>
              ))}
            </div>
            <div className="pipeline-sub-row" style={{ marginTop: 8 }}>
              <span className="pipeline-sub-label">Retrieve</span>
              <input
                type="number" min={5} max={200} step={5}
                value={cfg.rerank.candidate_k}
                className="input pipeline-number-input"
                onChange={e => setRerankInt('candidate_k', e.target.value)}
              />
              <span className="text-dim" style={{ fontSize: 10, margin: '0 6px' }}>→ top</span>
              <input
                type="number" min={1} max={50} step={1}
                value={cfg.rerank.top_n}
                className="input pipeline-number-input"
                onChange={e => setRerankInt('top_n', e.target.value)}
              />
            </div>
          </div>
        )}
      </div>

    </div>
  )
}

// ── SaveIndicator ─────────────────────────────────────────────────────────────

/** Shows transient save feedback next to the panel title. */
function SaveIndicator({ state }: { state: 'idle' | 'saving' | 'saved' | 'error' }) {
  if (state === 'idle') return null
  const meta: Record<string, { text: string; color: string }> = {
    saving: { text: 'saving…', color: 'var(--text-dim)' },
    saved:  { text: '✓ saved', color: 'var(--s-done)' },
    error:  { text: '✗ error', color: 'var(--s-error)' },
  }
  const m = meta[state]
  return (
    <span style={{ fontSize: 10, fontFamily: 'var(--font-mono)', color: m.color }}>
      {m.text}
    </span>
  )
}
