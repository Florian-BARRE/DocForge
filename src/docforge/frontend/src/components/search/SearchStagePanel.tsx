// ====== Code Summary ======
// SearchStagePanel — hardcoded configuration panel for the four search pipeline stages
// (transform, embed, retrieve, rerank).  Unlike StageConfigPanel it doesn't rely on
// discovery fields; instead it reads and writes directly into configState.pipeline.search.
// Changes are debounced 600 ms and persisted via updateConfig.

// ====== Third-Party Library Imports ======
import { useCallback, useEffect, useRef, useState } from 'react'

// ====== Internal Project Imports ======
import { updateConfig } from '../../api/client'
import type { ConfigState } from '../../api/types'

// ── Types ─────────────────────────────────────────────────────────────────────

/** The four stages supported by this panel. */
type SearchStageId = 'transform' | 'embed' | 'retrieve' | 'rerank'

interface SearchStagePanelProps {
  /** Which stage is being displayed. */
  stageId: SearchStageId
  /** Active collection — used when persisting changes. */
  collectionId: string
  /** Current persisted config state for the collection. */
  configState: ConfigState | null
  /** Called after a successful save so the parent can refresh its copy. */
  onSaved?: () => void
}

type SaveState = 'idle' | 'saving' | 'saved' | 'error'

// Strategy type shared by several helpers.
type TransformStrategy = 'none' | 'rewrite' | 'hyde' | 'multi_query'

// ── Helpers ───────────────────────────────────────────────────────────────────

/**
 * Extract the `pipeline.search` sub-object from a ConfigState instance.
 *
 * Args:
 *   cfg: Current collection config state or null.
 *
 * Returns:
 *   Record<string, unknown>: The search sub-config, or an empty object when absent.
 */
function extractSearchCfg(cfg: ConfigState | null): Record<string, unknown> {
  if (!cfg) return {}
  const pipeline = cfg.pipeline as Record<string, unknown>
  return (pipeline?.search as Record<string, unknown>) ?? {}
}

/**
 * Return a human-readable description for each transform strategy.
 *
 * Args:
 *   strategy: Active transform strategy identifier.
 *
 * Returns:
 *   string: Short description shown below the strategy selector.
 */
function strategyDescription(strategy: TransformStrategy): string {
  switch (strategy) {
    case 'none':        return 'Direct embedding — no query transformation.'
    case 'rewrite':     return 'LLM rewrites the query for better recall.'
    case 'hyde':        return 'Generates a hypothetical passage, then retrieves similar documents.'
    case 'multi_query': return 'Generates N query variants and fuses results with RRF.'
  }
}

// ── Component ─────────────────────────────────────────────────────────────────

/**
 * Hardcoded configuration panel for the search pipeline stages.
 *
 * Renders a different form section depending on `stageId`:
 *   - transform  : strategy selector + LLM provider + n_variants (multi_query only)
 *   - embed      : read-only info about the derived embed provider
 *   - retrieve   : top_k + score_threshold
 *   - rerank     : enabled toggle + provider + top_k + score_threshold
 *
 * All writable stages auto-save after a 600 ms debounce.  The patch sent to the
 * backend covers only the section that changed, wrapped as
 * `{ pipeline: { search: { <section>: ... } } }`.
 *
 * Args:
 *   stageId:      Which stage to render.
 *   collectionId: Target collection for config persistence.
 *   configState:  Current server-side config (seeds local form state).
 *   onSaved:      Optional callback fired after a successful save.
 */
export function SearchStagePanel({
  stageId,
  collectionId,
  configState,
  onSaved,
}: SearchStagePanelProps) {
  const [saveState, setSaveState] = useState<SaveState>('idle')
  const saveTimer = useRef<ReturnType<typeof setTimeout> | null>(null)
  // Prevents the first render from triggering an immediate save.
  const skipNextSave = useRef(true)

  // Reset skip guard when the collection or stage changes.
  useEffect(() => {
    skipNextSave.current = true
  }, [collectionId, stageId])

  /**
   * Schedule a debounced PATCH to the backend.
   *
   * The patch covers only the section relevant to the active stage so other
   * search config sections are not accidentally overwritten.
   *
   * Args:
   *   section: Key inside pipeline.search to update ('strategy', 'query_transform', 'retrieve', 'rerank').
   *   value:   Partial value for that section.
   */
  const scheduleSave = useCallback(
    (patch: Record<string, unknown>) => {
      if (saveTimer.current) clearTimeout(saveTimer.current)
      setSaveState('saving')
      saveTimer.current = setTimeout(async () => {
        try {
          await updateConfig(
            collectionId,
            { pipeline: { search: patch } },
            `Updated search ${stageId} config`,
          )
          setSaveState('saved')
          onSaved?.()
          setTimeout(() => setSaveState('idle'), 1500)
        } catch {
          setSaveState('error')
          setTimeout(() => setSaveState('idle'), 3000)
        }
      }, 600)
    },
    [collectionId, stageId, onSaved],
  )

  /**
   * Trigger a save unless this is the first call after a config seed.
   *
   * Args:
   *   patch: Partial pipeline.search patch to persist.
   */
  function maybeSave(patch: Record<string, unknown>) {
    if (skipNextSave.current) {
      skipNextSave.current = false
      return
    }
    scheduleSave(patch)
  }

  // ── Stage-specific sections ───────────────────────────────────────────────

  return (
    <div className="stage-config-panel">
      {/* Auto-save indicator row */}
      <div className="stage-config-save-indicator">
        <SaveIndicator state={saveState} />
      </div>

      {stageId === 'transform' && (
        <TransformSection
          configState={configState}
          onSave={maybeSave}
          searchCfg={extractSearchCfg(configState)}
        />
      )}
      {stageId === 'embed' && (
        <EmbedSection configState={configState} />
      )}
      {stageId === 'retrieve' && (
        <RetrieveSection
          searchCfg={extractSearchCfg(configState)}
          onSave={maybeSave}
        />
      )}
      {stageId === 'rerank' && (
        <RerankSection
          searchCfg={extractSearchCfg(configState)}
          onSave={maybeSave}
        />
      )}
    </div>
  )
}

// ── TransformSection ──────────────────────────────────────────────────────────

interface TransformSectionProps {
  configState: ConfigState | null
  searchCfg: Record<string, unknown>
  onSave: (patch: Record<string, unknown>) => void
}

/**
 * Configuration form for the query transform stage.
 *
 * Controls the transform strategy (none / rewrite / hyde / multi_query),
 * the optional LLM provider string, and the number of query variants for
 * the multi_query strategy.
 *
 * Args:
 *   configState: Full collection config state (used to seed form values).
 *   searchCfg:   Extracted pipeline.search object.
 *   onSave:      Callback that receives the pipeline.search patch to persist.
 */
function TransformSection({ searchCfg, onSave }: TransformSectionProps) {
  const qtCfg = (searchCfg.query_transform as Record<string, unknown>) ?? {}

  // strategy is stored at pipeline.search.strategy (top-level of SearchConfig)
  // but the backend QueryTransformConfig also has strategy — we read from top-level.
  const [strategy, setStrategy] = useState<TransformStrategy>(
    (searchCfg.strategy as TransformStrategy | undefined) ?? 'none',
  )
  const [llmProvider, setLlmProvider] = useState<string>(
    (qtCfg.llm_provider as string | undefined) ?? '',
  )
  const [nVariants, setNVariants] = useState<number>(
    (qtCfg.n_variants as number | undefined) ?? 3,
  )

  // Re-seed when configState changes (e.g. parent refreshes after save).
  useEffect(() => {
    setStrategy((searchCfg.strategy as TransformStrategy | undefined) ?? 'none')
    const qt = (searchCfg.query_transform as Record<string, unknown>) ?? {}
    setLlmProvider((qt.llm_provider as string | undefined) ?? '')
    setNVariants((qt.n_variants as number | undefined) ?? 3)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [searchCfg])

  /**
   * Build the full pipeline.search patch covering both top-level strategy and
   * the nested query_transform section, then hand it to the parent.
   *
   * Args:
   *   newStrategy:   Updated strategy value (may be the current one).
   *   newLlm:        Updated LLM provider string.
   *   newNVariants:  Updated n_variants integer.
   */
  function buildAndSave(
    newStrategy: TransformStrategy,
    newLlm: string,
    newNVariants: number,
  ) {
    const patch: Record<string, unknown> = {
      strategy: newStrategy,
      query_transform: {
        n_variants: newNVariants,
        llm_provider: newLlm || null,
      },
    }
    onSave(patch)
  }

  function handleStrategyChange(s: TransformStrategy) {
    setStrategy(s)
    buildAndSave(s, llmProvider, nVariants)
  }

  function handleLlmChange(v: string) {
    setLlmProvider(v)
    buildAndSave(strategy, v, nVariants)
  }

  function handleNVariantsChange(v: number) {
    setNVariants(v)
    buildAndSave(strategy, llmProvider, v)
  }

  return (
    <div>
      {/* Strategy selector */}
      <div className="stage-panel-row" style={{ marginBottom: 10 }}>
        <label className="stage-panel-label">Strategy</label>
        <select
          className="input"
          value={strategy}
          onChange={e => handleStrategyChange(e.target.value as TransformStrategy)}
          style={{ flex: 1 }}
        >
          <option value="none">none</option>
          <option value="rewrite">rewrite</option>
          <option value="hyde">hyde</option>
          <option value="multi_query">multi_query</option>
        </select>
      </div>

      {/* Strategy description */}
      <div className="search-stage-description">
        {strategyDescription(strategy)}
      </div>

      {/* LLM provider — visible when strategy is not 'none' */}
      {strategy !== 'none' && (
        <div className="stage-panel-row" style={{ marginBottom: 10 }}>
          <label className="stage-panel-label">LLM Provider</label>
          <input
            className="input"
            type="text"
            placeholder="e.g. local_llm or openai_llm"
            value={llmProvider}
            onChange={e => handleLlmChange(e.target.value)}
            style={{ flex: 1 }}
          />
        </div>
      )}

      {/* n_variants — visible only for multi_query */}
      {strategy === 'multi_query' && (
        <div className="stage-panel-row" style={{ marginBottom: 10 }}>
          <label className="stage-panel-label">Variants</label>
          <input
            className="input"
            type="number"
            min={1}
            max={10}
            value={nVariants}
            onChange={e => handleNVariantsChange(Number(e.target.value))}
            style={{ width: 80 }}
          />
        </div>
      )}
    </div>
  )
}

// ── EmbedSection ──────────────────────────────────────────────────────────────

/**
 * Read-only information panel for the embed stage.
 *
 * The embed provider is always auto-derived from the collection's ingestion
 * config and cannot be changed in the search context.
 *
 * Args:
 *   configState: Full collection config state (provides embedding_model and locality_policy).
 */
function EmbedSection({ configState }: { configState: ConfigState | null }) {
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

// ── RetrieveSection ───────────────────────────────────────────────────────────

interface RetrieveSectionProps {
  searchCfg: Record<string, unknown>
  onSave: (patch: Record<string, unknown>) => void
}

/**
 * Configuration form for the retrieve stage.
 *
 * Controls the number of results returned from Qdrant (top_k) and an optional
 * minimum score threshold that filters out low-quality candidates.
 *
 * Args:
 *   searchCfg: Extracted pipeline.search object.
 *   onSave:    Callback that receives the pipeline.search patch to persist.
 */
function RetrieveSection({ searchCfg, onSave }: RetrieveSectionProps) {
  const retrieveCfg = (searchCfg.retrieve as Record<string, unknown>) ?? {}

  const [topK, setTopK] = useState<number>(
    (retrieveCfg.top_k as number | undefined) ?? 10,
  )
  const [scoreThreshold, setScoreThreshold] = useState<string>(
    retrieveCfg.score_threshold != null ? String(retrieveCfg.score_threshold) : '',
  )

  useEffect(() => {
    const rc = (searchCfg.retrieve as Record<string, unknown>) ?? {}
    setTopK((rc.top_k as number | undefined) ?? 10)
    setScoreThreshold(rc.score_threshold != null ? String(rc.score_threshold) : '')
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [searchCfg])

  function buildAndSave(newTopK: number, newThreshold: string) {
    onSave({
      retrieve: {
        top_k: newTopK,
        score_threshold: newThreshold !== '' ? parseFloat(newThreshold) : null,
      },
    })
  }

  return (
    <div>
      <div className="stage-panel-row" style={{ marginBottom: 10 }}>
        <label className="stage-panel-label">Top K results</label>
        <input
          className="input"
          type="number"
          min={1}
          value={topK}
          onChange={e => {
            const v = Number(e.target.value)
            setTopK(v)
            buildAndSave(v, scoreThreshold)
          }}
          style={{ width: 80 }}
        />
      </div>
      <div className="stage-panel-row">
        <label className="stage-panel-label">Score threshold</label>
        <input
          className="input"
          type="number"
          step={0.01}
          min={0}
          max={1}
          placeholder="No threshold"
          value={scoreThreshold}
          onChange={e => {
            setScoreThreshold(e.target.value)
            buildAndSave(topK, e.target.value)
          }}
          style={{ width: 100 }}
        />
      </div>
    </div>
  )
}

// ── RerankSection ─────────────────────────────────────────────────────────────

interface RerankSectionProps {
  searchCfg: Record<string, unknown>
  onSave: (patch: Record<string, unknown>) => void
}

/**
 * Configuration form for the rerank stage.
 *
 * Controls whether cross-encoder reranking is enabled, the rerank provider
 * identifier, and the number of results to return after reranking.
 *
 * Args:
 *   searchCfg: Extracted pipeline.search object.
 *   onSave:    Callback that receives the pipeline.search patch to persist.
 */
function RerankSection({ searchCfg, onSave }: RerankSectionProps) {
  const rerankCfg = (searchCfg.rerank as Record<string, unknown>) ?? {}

  const [enabled, setEnabled] = useState<boolean>(
    Boolean(rerankCfg.enabled ?? false),
  )
  const [provider, setProvider] = useState<string>(
    (rerankCfg.provider as string | undefined) ?? '',
  )
  const [topK, setTopK] = useState<string>(
    rerankCfg.top_k != null ? String(rerankCfg.top_k) : '',
  )
  const [scoreThreshold, setScoreThreshold] = useState<string>(
    rerankCfg.score_threshold != null ? String(rerankCfg.score_threshold) : '',
  )

  useEffect(() => {
    const rc = (searchCfg.rerank as Record<string, unknown>) ?? {}
    setEnabled(Boolean(rc.enabled ?? false))
    setProvider((rc.provider as string | undefined) ?? '')
    setTopK(rc.top_k != null ? String(rc.top_k) : '')
    setScoreThreshold(rc.score_threshold != null ? String(rc.score_threshold) : '')
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [searchCfg])

  function buildAndSave(
    newEnabled: boolean,
    newProvider: string,
    newTopK: string,
    newThreshold: string,
  ) {
    onSave({
      rerank: {
        enabled: newEnabled,
        provider: newProvider || null,
        top_k: newTopK !== '' ? parseInt(newTopK, 10) : null,
        score_threshold: newThreshold !== '' ? parseFloat(newThreshold) : null,
      },
    })
  }

  function handleEnabledChange(v: boolean) {
    setEnabled(v)
    buildAndSave(v, provider, topK, scoreThreshold)
  }

  return (
    <div>
      {/* Enable toggle */}
      <div className="stage-panel-row" style={{ marginBottom: 10 }}>
        <label className="stage-panel-label">Enable reranking</label>
        <input
          type="checkbox"
          checked={enabled}
          onChange={e => handleEnabledChange(e.target.checked)}
          style={{ width: 16, height: 16 }}
        />
      </div>

      {/* Additional fields — only when enabled */}
      {enabled && (
        <>
          <div className="stage-panel-row" style={{ marginBottom: 10 }}>
            <label className="stage-panel-label">Provider</label>
            <input
              className="input"
              type="text"
              placeholder="e.g. bge_reranker or cohere_rerank"
              value={provider}
              onChange={e => {
                setProvider(e.target.value)
                buildAndSave(enabled, e.target.value, topK, scoreThreshold)
              }}
              style={{ flex: 1 }}
            />
          </div>
          <div className="stage-panel-row" style={{ marginBottom: 10 }}>
            <label className="stage-panel-label">Return top K after rerank</label>
            <input
              className="input"
              type="number"
              min={1}
              placeholder="—"
              value={topK}
              onChange={e => {
                setTopK(e.target.value)
                buildAndSave(enabled, provider, e.target.value, scoreThreshold)
              }}
              style={{ width: 80 }}
            />
          </div>
          <div className="stage-panel-row">
            <label className="stage-panel-label">Score threshold</label>
            <input
              className="input"
              type="number"
              step={0.01}
              placeholder="—"
              value={scoreThreshold}
              onChange={e => {
                setScoreThreshold(e.target.value)
                buildAndSave(enabled, provider, topK, e.target.value)
              }}
              style={{ width: 100 }}
            />
          </div>
        </>
      )}
    </div>
  )
}

// ── SaveIndicator ─────────────────────────────────────────────────────────────

/**
 * Inline transient feedback label for auto-save state.
 *
 * Returns null when state is 'idle' so the indicator row collapses cleanly.
 *
 * Args:
 *   state: Current save lifecycle state.
 */
function SaveIndicator({ state }: { state: SaveState }) {
  if (state === 'idle') return null
  const meta: Record<string, { text: string; color: string }> = {
    saving: { text: 'saving…', color: 'var(--text-dim)' },
    saved:  { text: '✓ saved', color: 'var(--s-done)' },
    error:  { text: '✗ error', color: 'var(--s-error)' },
  }
  const m = meta[state]
  return <span style={{ color: m.color }}>{m.text}</span>
}
