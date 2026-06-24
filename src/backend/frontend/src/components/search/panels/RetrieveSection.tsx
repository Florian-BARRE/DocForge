// ====== Code Summary ======
// RetrieveSection — configuration form for the retrieve stage of the search
// pipeline (pipeline.search.retrieve). Exposes the full RetrieveConfig contract:
// vector mode, fusion algorithm, RRF k, score threshold, candidate sizing, content
// vector weights, per-field fusion weights, and the advanced grouping / MMR toggles.

// ====== Third-Party Library Imports ======
import { useEffect, useState } from 'react'

// ====== Internal Project Imports ======
import type { ConfigState, MetaField } from '../../../api/types'

// ── Types ─────────────────────────────────────────────────────────────────────

export interface RetrieveSectionProps {
  /** Full collection config — used to read metadata_fields for per-field weights. */
  configState: ConfigState | null
  searchCfg: Record<string, unknown>
  onSave: (patch: Record<string, unknown>) => void
}

type VectorMode = 'hybrid' | 'dense' | 'sparse'
type FusionMode = 'rrf' | 'dbsf'

// ── Helpers ───────────────────────────────────────────────────────────────────

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

// ── Component ─────────────────────────────────────────────────────────────────

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
export function RetrieveSection({ configState, searchCfg, onSave }: RetrieveSectionProps) {
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
