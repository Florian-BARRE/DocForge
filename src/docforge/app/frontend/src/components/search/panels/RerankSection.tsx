// ====== Code Summary ======
// RerankSection — configuration form for the rerank stage of the search pipeline
// (pipeline.search.rerank). Controls whether cross-encoder reranking is enabled
// and the number of candidates fed to the reranker (candidate_k). The final
// result count is determined by the request top_k, not a config field.

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
 * Controls whether cross-encoder reranking is enabled and the number of
 * candidates fed to the reranker (candidate_k). The final result count is the
 * request top_k — there is no separate top_n config field. The rerank provider
 * chain is an advanced provider config and is intentionally not editable here.
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

  useEffect(() => {
    const rc = (searchCfg.rerank as Record<string, unknown>) ?? {}
    setEnabled(Boolean(rc.enabled ?? false))
    setCandidateK((rc.candidate_k as number | undefined) ?? 50)
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

      {/* Candidate K — only when enabled */}
      {enabled && (
        <div className="stage-panel-row">
          <label className="stage-panel-label">Candidates fed to reranker</label>
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
      )}
    </div>
  )
}
