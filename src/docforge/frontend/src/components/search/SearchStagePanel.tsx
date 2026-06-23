// ====== Code Summary ======
// SearchStagePanel — hardcoded configuration panel for the four search pipeline stages
// (transform, embed, retrieve, rerank).  Unlike StageConfigPanel it doesn't rely on
// discovery fields; instead it reads and writes directly into configState.pipeline.search.
// Edits accumulate in a local draft buffer (useConfigDraft) and are persisted only when
// the user clicks Save in the ConfigSaveBar at the bottom. The embed stage is read-only.

// ====== Third-Party Library Imports ======
import { useEffect, useState } from 'react'

// ====== Internal Project Imports ======
import type { ConfigState, MetaField } from '../../api/types'
import { useConfigDraft } from '../../hooks/useConfigDraft'
import { ConfigSaveBar } from '../ui/ConfigSaveBar'

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
 *   - transform  : query_transform.strategy + n_variants (multi_query only)
 *   - embed      : read-only info about the derived embed provider
 *   - retrieve   : full retrieve config (vector mode, fusion, weights, field
 *                  weights, grouping, MMR)
 *   - rerank     : enabled toggle + candidate_k + top_n
 *
 * Edits stage a partial `pipeline.search` patch into the shared draft buffer;
 * nothing is sent to the server until the user clicks Save in the bottom
 * ConfigSaveBar. The patch is wrapped as `{ pipeline: { search: { ... } } }`.
 * The embed stage is read-only and shows no save bar.
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
  // ── Draft buffer (shared explicit save/discard workflow) ──────────────────
  const draft = useConfigDraft(collectionId, onSaved)

  // Reset nonce: bumped on discard so the active section remounts and re-seeds
  // its local form state from configState (which is unchanged on discard).
  const [resetNonce, setResetNonce] = useState(0)

  /**
   * Stage a partial pipeline.search patch into the draft buffer.
   *
   * The patch covers only the section relevant to the active stage so other
   * search config sections are not accidentally overwritten.
   *
   * Args:
   *   patch: Partial pipeline.search patch to accumulate.
   */
  function handleSave(patch: Record<string, unknown>) {
    draft.stage({ pipeline: { search: patch } })
  }

  /** Discard the draft buffer and force the active section to re-seed. */
  function handleDiscard() {
    draft.discard()
    setResetNonce(n => n + 1)
  }

  const searchCfg = extractSearchCfg(configState)
  // Section key combines stage + nonce so a discard remounts the section,
  // restoring its local state from the (unchanged) persisted config.
  const sectionKey = `${stageId}-${resetNonce}`

  // ── Stage-specific sections ───────────────────────────────────────────────

  return (
    <div className="stage-config-panel">
      {stageId === 'transform' && (
        <TransformSection
          key={sectionKey}
          configState={configState}
          onSave={handleSave}
          searchCfg={searchCfg}
        />
      )}
      {stageId === 'embed' && (
        <EmbedSection configState={configState} />
      )}
      {stageId === 'retrieve' && (
        <RetrieveSection
          key={sectionKey}
          configState={configState}
          searchCfg={searchCfg}
          onSave={handleSave}
        />
      )}
      {stageId === 'rerank' && (
        <RerankSection
          key={sectionKey}
          searchCfg={searchCfg}
          onSave={handleSave}
        />
      )}

      {/* Save bar for all writable stages (embed is read-only). */}
      {stageId !== 'embed' && (
        <ConfigSaveBar
          status={draft.status}
          isDirty={draft.isDirty}
          onSave={() => { void draft.save() }}
          onDiscard={handleDiscard}
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
 * Controls the transform strategy (none / rewrite / hyde / multi_query) and the
 * number of query variants for the multi_query strategy. Both values live under
 * `pipeline.search.query_transform`. The LLM provider config is an advanced
 * provider object and is intentionally not editable here.
 *
 * Args:
 *   searchCfg: Extracted pipeline.search object.
 *   onSave:    Callback that receives the pipeline.search patch to persist.
 */
function TransformSection({ searchCfg, onSave }: TransformSectionProps) {
  const qtCfg = (searchCfg.query_transform as Record<string, unknown>) ?? {}

  // Strategy and n_variants both live under pipeline.search.query_transform.
  const [strategy, setStrategy] = useState<TransformStrategy>(
    (qtCfg.strategy as TransformStrategy | undefined) ?? 'none',
  )
  const [nVariants, setNVariants] = useState<number>(
    (qtCfg.n_variants as number | undefined) ?? 3,
  )

  // Re-seed when configState changes (e.g. parent refreshes after save).
  useEffect(() => {
    const qt = (searchCfg.query_transform as Record<string, unknown>) ?? {}
    setStrategy((qt.strategy as TransformStrategy | undefined) ?? 'none')
    setNVariants((qt.n_variants as number | undefined) ?? 3)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [searchCfg])

  /**
   * Build the query_transform patch and hand it to the parent for persistence.
   *
   * Args:
   *   newStrategy:  Updated strategy value (may be the current one).
   *   newNVariants: Updated n_variants integer.
   */
  function buildAndSave(newStrategy: TransformStrategy, newNVariants: number) {
    onSave({
      query_transform: {
        strategy: newStrategy,
        n_variants: newNVariants,
      },
    })
  }

  function handleStrategyChange(s: TransformStrategy) {
    setStrategy(s)
    buildAndSave(s, nVariants)
  }

  function handleNVariantsChange(v: number) {
    setNVariants(v)
    buildAndSave(strategy, v)
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
  /** Full collection config — used to read metadata_fields for per-field weights. */
  configState: ConfigState | null
  searchCfg: Record<string, unknown>
  onSave: (patch: Record<string, unknown>) => void
}

type VectorMode = 'hybrid' | 'dense' | 'sparse'
type FusionMode = 'rrf' | 'dbsf'

/**
 * Return a short description for the selected vector mode.
 *
 * Args:
 *   mode: Active vector retrieval mode.
 *
 * Returns:
 *   string: Human-readable description shown below the selector.
 */
function vectorModeDescription(mode: VectorMode): string {
  switch (mode) {
    case 'hybrid': return 'Dense semantic + sparse keyword (BM25)'
    case 'dense':  return 'Semantic vectors only'
    case 'sparse': return 'Keyword/BM25 only'
  }
}

/**
 * Return a short description for the selected fusion mode.
 *
 * Args:
 *   mode: Active fusion algorithm.
 *
 * Returns:
 *   string: Human-readable description shown below the selector.
 */
function fusionModeDescription(mode: FusionMode): string {
  switch (mode) {
    case 'rrf':  return 'Reciprocal Rank Fusion — robust, rank-based'
    case 'dbsf': return 'Distribution-Based Score Fusion — normalizes raw scores'
  }
}

/**
 * Configuration form for the retrieve stage (pipeline.search.retrieve).
 *
 * Exposes the full RetrieveConfig contract: vector mode, fusion algorithm, RRF k,
 * score threshold, candidate sizing, content vector weights, per-field fusion
 * weights, and the advanced grouping / MMR toggles. Every control auto-saves a
 * partial `{ retrieve: { ... } }` patch (the backend deep-merges it).
 *
 * Note: `top_k` is a query parameter (SearchRequest.top_k), not part of this
 * config — it is intentionally absent here.
 *
 * Args:
 *   configState: Full collection config state (provides metadata_fields).
 *   searchCfg:   Extracted pipeline.search object.
 *   onSave:      Callback that receives the pipeline.search patch to persist.
 */
function RetrieveSection({ configState, searchCfg, onSave }: RetrieveSectionProps) {
  const retrieveCfg = (searchCfg.retrieve as Record<string, unknown>) ?? {}

  // ── Local form state ────────────────────────────────────────────────────────
  const [vectorMode, setVectorMode] = useState<VectorMode>(
    (retrieveCfg.vector_mode as VectorMode | undefined) ?? 'hybrid',
  )
  const [fusion, setFusion] = useState<FusionMode>(
    (retrieveCfg.fusion as FusionMode | undefined) ?? 'rrf',
  )
  const [rrfK, setRrfK] = useState<number>(
    (retrieveCfg.rrf_k as number | undefined) ?? 60,
  )
  const [scoreThreshold, setScoreThreshold] = useState<string>(
    retrieveCfg.score_threshold != null ? String(retrieveCfg.score_threshold) : '',
  )
  const [candidateMultiplier, setCandidateMultiplier] = useState<number>(
    (retrieveCfg.candidate_multiplier as number | undefined) ?? 3,
  )
  const [minCandidates, setMinCandidates] = useState<number>(
    (retrieveCfg.min_candidates as number | undefined) ?? 20,
  )
  const [contentDenseWeight, setContentDenseWeight] = useState<number>(
    (retrieveCfg.content_dense_weight as number | undefined) ?? 1.0,
  )
  const [contentSparseWeight, setContentSparseWeight] = useState<number>(
    (retrieveCfg.content_sparse_weight as number | undefined) ?? 1.0,
  )
  const [fieldWeights, setFieldWeights] = useState<Record<string, number>>(
    (retrieveCfg.field_weights as Record<string, number> | undefined) ?? {},
  )

  const groupingCfg = (retrieveCfg.grouping as Record<string, unknown>) ?? {}
  const mmrCfg = (retrieveCfg.mmr as Record<string, unknown>) ?? {}
  const [groupingEnabled, setGroupingEnabled] = useState<boolean>(
    Boolean(groupingCfg.enabled ?? false),
  )
  const [groupSize, setGroupSize] = useState<number>(
    (groupingCfg.group_size as number | undefined) ?? 3,
  )
  const [mmrEnabled, setMmrEnabled] = useState<boolean>(
    Boolean(mmrCfg.enabled ?? false),
  )
  const [mmrDiversity, setMmrDiversity] = useState<number>(
    (mmrCfg.diversity as number | undefined) ?? 0.5,
  )

  // Re-seed all fields when the persisted config changes.
  useEffect(() => {
    const rc = (searchCfg.retrieve as Record<string, unknown>) ?? {}
    setVectorMode((rc.vector_mode as VectorMode | undefined) ?? 'hybrid')
    setFusion((rc.fusion as FusionMode | undefined) ?? 'rrf')
    setRrfK((rc.rrf_k as number | undefined) ?? 60)
    setScoreThreshold(rc.score_threshold != null ? String(rc.score_threshold) : '')
    setCandidateMultiplier((rc.candidate_multiplier as number | undefined) ?? 3)
    setMinCandidates((rc.min_candidates as number | undefined) ?? 20)
    setContentDenseWeight((rc.content_dense_weight as number | undefined) ?? 1.0)
    setContentSparseWeight((rc.content_sparse_weight as number | undefined) ?? 1.0)
    setFieldWeights((rc.field_weights as Record<string, number> | undefined) ?? {})
    const g = (rc.grouping as Record<string, unknown>) ?? {}
    setGroupingEnabled(Boolean(g.enabled ?? false))
    setGroupSize((g.group_size as number | undefined) ?? 3)
    const m = (rc.mmr as Record<string, unknown>) ?? {}
    setMmrEnabled(Boolean(m.enabled ?? false))
    setMmrDiversity((m.diversity as number | undefined) ?? 0.5)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [searchCfg])

  // ── Searchable fields (have a vector → can carry a fusion weight) ────────────
  const searchableFields: MetaField[] = (configState?.metadata_fields ?? []).filter(
    f => f.semantic || f.lexical,
  )

  // ── Field weight handler ────────────────────────────────────────────────────
  /**
   * Update one field's fusion weight and persist the whole field_weights map.
   *
   * Args:
   *   fieldName: Metadata field whose weight changed.
   *   weight:    New numeric weight for that field.
   */
  function handleFieldWeightChange(fieldName: string, weight: number) {
    const next = { ...fieldWeights, [fieldName]: weight }
    setFieldWeights(next)
    onSave({ retrieve: { field_weights: next } })
  }

  return (
    <div>
      {/* ── Vector mode ── */}
      <div className="stage-panel-row" style={{ marginBottom: 4 }}>
        <label className="stage-panel-label">Vector mode</label>
        <select
          className="input"
          value={vectorMode}
          onChange={e => {
            const v = e.target.value as VectorMode
            setVectorMode(v)
            onSave({ retrieve: { vector_mode: v } })
          }}
          style={{ flex: 1 }}
        >
          <option value="hybrid">hybrid</option>
          <option value="dense">dense</option>
          <option value="sparse">sparse</option>
        </select>
      </div>
      <div className="search-stage-description">{vectorModeDescription(vectorMode)}</div>

      {/* ── Fusion ── */}
      <div className="stage-panel-row" style={{ marginBottom: 4 }}>
        <label className="stage-panel-label">Fusion</label>
        <select
          className="input"
          value={fusion}
          onChange={e => {
            const v = e.target.value as FusionMode
            setFusion(v)
            onSave({ retrieve: { fusion: v } })
          }}
          style={{ flex: 1 }}
        >
          <option value="rrf">rrf</option>
          <option value="dbsf">dbsf</option>
        </select>
      </div>
      <div className="search-stage-description">{fusionModeDescription(fusion)}</div>

      {/* ── RRF k (only when fusion=rrf) ── */}
      {fusion === 'rrf' && (
        <div className="stage-panel-row" style={{ marginBottom: 4 }}>
          <label className="stage-panel-label">RRF k</label>
          <input
            className="input"
            type="number"
            min={1}
            value={rrfK}
            onChange={e => {
              const v = Number(e.target.value)
              setRrfK(v)
              onSave({ retrieve: { rrf_k: v } })
            }}
            style={{ width: 90 }}
          />
        </div>
      )}
      {fusion === 'rrf' && (
        <div className="search-stage-description">Higher = flatter rank influence (standard 60)</div>
      )}

      {/* ── Score threshold (nullable) ── */}
      <div className="stage-panel-row" style={{ marginBottom: 4 }}>
        <label className="stage-panel-label">Score threshold</label>
        <input
          className="input"
          type="number"
          step={0.01}
          placeholder="No cutoff"
          value={scoreThreshold}
          onChange={e => {
            const raw = e.target.value
            setScoreThreshold(raw)
            onSave({
              retrieve: { score_threshold: raw !== '' ? parseFloat(raw) : null },
            })
          }}
          style={{ width: 110 }}
        />
      </div>
      <div className="search-stage-description">Minimum per-vector similarity</div>

      {/* ── Candidate sizing ── */}
      <div className="stage-panel-row" style={{ marginBottom: 4 }}>
        <label className="stage-panel-label">Candidate sizing</label>
        <div style={{ display: 'flex', gap: 8, flex: 1 }}>
          <label style={{ display: 'flex', flexDirection: 'column', gap: 2, fontSize: 10, color: 'var(--text-dim)' }}>
            Candidate ×
            <input
              className="input"
              type="number"
              min={1}
              value={candidateMultiplier}
              onChange={e => {
                const v = Number(e.target.value)
                setCandidateMultiplier(v)
                onSave({ retrieve: { candidate_multiplier: v } })
              }}
              style={{ width: 80 }}
            />
          </label>
          <label style={{ display: 'flex', flexDirection: 'column', gap: 2, fontSize: 10, color: 'var(--text-dim)' }}>
            Min candidates
            <input
              className="input"
              type="number"
              min={1}
              value={minCandidates}
              onChange={e => {
                const v = Number(e.target.value)
                setMinCandidates(v)
                onSave({ retrieve: { min_candidates: v } })
              }}
              style={{ width: 90 }}
            />
          </label>
        </div>
      </div>
      <div className="search-stage-description">Pool per vector = max(top_k × mult, min)</div>

      {/* ── Content weights ── */}
      <div className="stage-panel-row" style={{ marginBottom: 4 }}>
        <label className="stage-panel-label">Content weights</label>
        <div style={{ display: 'flex', gap: 8, flex: 1 }}>
          <label style={{ display: 'flex', flexDirection: 'column', gap: 2, fontSize: 10, color: 'var(--text-dim)' }}>
            Dense
            <input
              className="input"
              type="number"
              step={0.1}
              min={0}
              value={contentDenseWeight}
              onChange={e => {
                const v = Number(e.target.value)
                setContentDenseWeight(v)
                onSave({ retrieve: { content_dense_weight: v } })
              }}
              style={{ width: 80 }}
            />
          </label>
          <label style={{ display: 'flex', flexDirection: 'column', gap: 2, fontSize: 10, color: 'var(--text-dim)' }}>
            Keyword
            <input
              className="input"
              type="number"
              step={0.1}
              min={0}
              value={contentSparseWeight}
              onChange={e => {
                const v = Number(e.target.value)
                setContentSparseWeight(v)
                onSave({ retrieve: { content_sparse_weight: v } })
              }}
              style={{ width: 80 }}
            />
          </label>
        </div>
      </div>

      {/* ── Per-field weights ── */}
      <div className="search-overview-title" style={{ marginTop: 14 }}>Field weights</div>
      {searchableFields.length === 0 ? (
        <div className="stage-config-empty" style={{ fontSize: 11 }}>
          No searchable metadata fields. Mark fields as semantic or lexical in the pipeline config.
        </div>
      ) : (
        searchableFields.map(field => (
          <div className="field-weight-row" key={field.field_name}>
            <span className="field-weight-name">{field.field_name}</span>
            {field.semantic && <span className="field-weight-badge">sem</span>}
            {field.lexical && <span className="field-weight-badge">lex</span>}
            <input
              className="input input-sm"
              type="number"
              step={0.1}
              min={0}
              value={fieldWeights[field.field_name] ?? 1.0}
              onChange={e => handleFieldWeightChange(field.field_name, Number(e.target.value))}
              style={{ width: 70 }}
            />
          </div>
        ))
      )}

      {/* ── Advanced: grouping + MMR ── */}
      <div className="search-overview-title" style={{ marginTop: 14 }}>Advanced</div>

      {/* Grouping */}
      <div className="stage-panel-row" style={{ marginBottom: 4 }}>
        <label className="stage-panel-label">Group results by document</label>
        <input
          type="checkbox"
          checked={groupingEnabled}
          onChange={e => {
            const v = e.target.checked
            setGroupingEnabled(v)
            onSave({ retrieve: { grouping: { enabled: v, group_size: groupSize } } })
          }}
          style={{ width: 16, height: 16 }}
        />
      </div>
      {groupingEnabled && (
        <div className="stage-panel-row" style={{ marginBottom: 4 }}>
          <label className="stage-panel-label">Chunks per document</label>
          <input
            className="input"
            type="number"
            min={1}
            max={20}
            value={groupSize}
            onChange={e => {
              const v = Number(e.target.value)
              setGroupSize(v)
              onSave({ retrieve: { grouping: { enabled: groupingEnabled, group_size: v } } })
            }}
            style={{ width: 80 }}
          />
        </div>
      )}

      {/* MMR */}
      <div className="stage-panel-row" style={{ marginBottom: 4 }}>
        <label className="stage-panel-label">Diversify results (MMR)</label>
        <input
          type="checkbox"
          checked={mmrEnabled}
          onChange={e => {
            const v = e.target.checked
            setMmrEnabled(v)
            onSave({ retrieve: { mmr: { enabled: v, diversity: mmrDiversity } } })
          }}
          style={{ width: 16, height: 16 }}
        />
      </div>
      {mmrEnabled && (
        <div className="stage-panel-row" style={{ marginBottom: 4 }}>
          <label className="stage-panel-label">Diversity (0=relevance, 1=diversity)</label>
          <input
            className="input"
            type="number"
            step={0.05}
            min={0}
            max={1}
            value={mmrDiversity}
            onChange={e => {
              const v = Number(e.target.value)
              setMmrDiversity(v)
              onSave({ retrieve: { mmr: { enabled: mmrEnabled, diversity: v } } })
            }}
            style={{ width: 90 }}
          />
        </div>
      )}
    </div>
  )
}

// ── RerankSection ─────────────────────────────────────────────────────────────

interface RerankSectionProps {
  searchCfg: Record<string, unknown>
  onSave: (patch: Record<string, unknown>) => void
}

/**
 * Configuration form for the rerank stage (pipeline.search.rerank).
 *
 * Controls whether cross-encoder reranking is enabled, the number of candidates
 * fed to the reranker (candidate_k), and the number of results kept after
 * reranking (top_n). The rerank provider chain is an advanced provider config
 * and is intentionally not editable here.
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
  const [candidateK, setCandidateK] = useState<number>(
    (rerankCfg.candidate_k as number | undefined) ?? 50,
  )
  const [topN, setTopN] = useState<number>(
    (rerankCfg.top_n as number | undefined) ?? 10,
  )

  useEffect(() => {
    const rc = (searchCfg.rerank as Record<string, unknown>) ?? {}
    setEnabled(Boolean(rc.enabled ?? false))
    setCandidateK((rc.candidate_k as number | undefined) ?? 50)
    setTopN((rc.top_n as number | undefined) ?? 10)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [searchCfg])

  return (
    <div>
      {/* Enable toggle */}
      <div className="stage-panel-row" style={{ marginBottom: 10 }}>
        <label className="stage-panel-label">Enable reranking</label>
        <input
          type="checkbox"
          checked={enabled}
          onChange={e => {
            const v = e.target.checked
            setEnabled(v)
            onSave({ rerank: { enabled: v } })
          }}
          style={{ width: 16, height: 16 }}
        />
      </div>

      {/* Additional fields — only when enabled */}
      {enabled && (
        <>
          <div className="stage-panel-row" style={{ marginBottom: 10 }}>
            <label className="stage-panel-label">Candidate K (fed to reranker)</label>
            <input
              className="input"
              type="number"
              min={1}
              value={candidateK}
              onChange={e => {
                const v = Number(e.target.value)
                setCandidateK(v)
                onSave({ rerank: { candidate_k: v } })
              }}
              style={{ width: 90 }}
            />
          </div>
          <div className="stage-panel-row">
            <label className="stage-panel-label">Top N (kept after rerank)</label>
            <input
              className="input"
              type="number"
              min={1}
              value={topN}
              onChange={e => {
                const v = Number(e.target.value)
                setTopN(v)
                onSave({ rerank: { top_n: v } })
              }}
              style={{ width: 90 }}
            />
          </div>
        </>
      )}
    </div>
  )
}
