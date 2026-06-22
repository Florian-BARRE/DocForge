// ====== Code Summary ======
// Static definitions of the search pipeline stages used in SearchTab's PipelineGraph.
// Each stage maps to a fieldPathPrefix used to filter discovery fields in StageConfigPanel.

import type { StageDefinition } from './types'

/**
 * Ordered list of search pipeline stage definitions for the SearchTab graph.
 *
 * These four stages mirror the backend SearchPipelineEngine steps:
 * query transform → embed → retrieve → rerank.
 *
 * The `embed` stage is marked `readOnly` because its provider is always
 * auto-derived from the collection's ingestion embed config and cannot be
 * changed independently in the search context.
 */
export const SEARCH_STAGES: StageDefinition[] = [
  {
    id: 'transform',
    label: 'Transform',
    icon: '🔄',
    fieldPathPrefix: 'pipeline.search.query_transform',
    optional: false,
  },
  {
    id: 'embed',
    label: 'Embed',
    icon: '🔢',
    fieldPathPrefix: 'pipeline.embed',
    optional: false,
    // Auto-derived from the collection's ingestion embed config — not configurable here.
    readOnly: true,
  },
  {
    id: 'retrieve',
    label: 'Retrieve',
    icon: '🔍',
    fieldPathPrefix: 'pipeline.search.retrieve',
    optional: false,
  },
  {
    id: 'rerank',
    label: 'Rerank',
    icon: '📊',
    fieldPathPrefix: 'pipeline.search.rerank',
    optional: true,
  },
]
