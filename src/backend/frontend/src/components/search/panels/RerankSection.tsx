// ====== Code Summary ======
// RerankSection — configuration form for the rerank stage of the search pipeline
// (pipeline.search.rerank). Controls whether cross-encoder reranking is enabled,
// the number of candidates fed to the reranker (candidate_k), and the number of
// results kept after reranking (top_n).

// ====== Third-Party Library Imports ======
import { useEffect, useState } from 'react'

// ── Types ─────────────────────────────────────────────────────────────────────

export interface RerankSectionProps {
  searchCfg: Record<string, unknown>
  onSave: (patch: Record<string, unknown>) => void
}

// ── Component ─────────────────────────────────────────────────────────────────

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
export function RerankSection({ searchCfg, onSave }: RerankSectionProps) {
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
