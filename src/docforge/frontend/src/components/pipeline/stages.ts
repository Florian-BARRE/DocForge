// ====== Code Summary ======
// Static definitions of the ingestion pipeline stages used by PipelineGraph.
// No API calls — these are pure constants describing each stage's identity and
// the field_path prefix used to filter discovery fields in the config panel.

// ====== Local Project Imports ======
import type { StageDefinition } from './types'

/**
 * Ordered list of ingestion pipeline stage definitions.
 *
 * Each entry describes a single stage node rendered by {@link PipelineGraph}.
 * The `fieldPathPrefix` is used by {@link StageConfigPanel} to filter the
 * relevant dynamic fields out of the full discovery payload.
 */
export const INGESTION_STAGES: StageDefinition[] = [
  {
    id: 's0',
    label: 'Ingest',
    icon: '📥',
    fieldPathPrefix: 'pipeline.ingest',
    optional: false,
  },
  {
    id: 's1',
    label: 'Parse',
    icon: '🔍',
    fieldPathPrefix: 'pipeline.parse',
    optional: false,
  },
  {
    id: 's2',
    label: 'Enrich',
    icon: '✨',
    fieldPathPrefix: 'pipeline.enrich',
    // S2 is opt-in — rendered with a dashed border to signal that it is
    // disabled by default and must be explicitly enabled per collection.
    optional: true,
  },
  {
    id: 's4',
    label: 'Chunk',
    icon: '✂️',
    fieldPathPrefix: 'pipeline.chunk',
    optional: false,
  },
  {
    id: 's5',
    label: 'Context',
    icon: '🧩',
    fieldPathPrefix: 'pipeline.contextualize',
    optional: false,
  },
  {
    id: 's6',
    label: 'Embed',
    icon: '🔢',
    fieldPathPrefix: 'pipeline.embed',
    optional: false,
  },
]
