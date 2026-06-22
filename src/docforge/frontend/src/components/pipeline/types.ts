// ====== Code Summary ======
// Shared type definitions for the PipelineGraph system.

/**
 * Static definition of a single pipeline stage (identity + display metadata).
 * Instances are declared once and passed down as props — never mutated at runtime.
 */
export interface StageDefinition {
  /** Short identifier used as a key, e.g. "s0", "s1", "s4". */
  id: string
  /** Human-readable label shown inside the node, e.g. "Ingest", "Parse". */
  label: string
  /** Emoji or short glyph displayed as the stage icon. */
  icon: string
  /** Prefix used to filter relevant config fields in a discovery panel. */
  fieldPathPrefix: string
  /** If true, the stage is opt-in and rendered with a dashed border. */
  optional?: boolean
  /** If true, the stage cannot be configured and shows no hover gear. */
  readOnly?: boolean
}

/**
 * All possible lifecycle states a stage can be in during a pipeline trace.
 */
export type StageStatus = 'done' | 'running' | 'error' | 'skipped' | 'pending'

/**
 * Runtime result for a single stage, populated only in trace mode.
 */
export interface StageResult {
  /** Current lifecycle state of the stage. */
  status: StageStatus
  /** Wall-clock duration of the stage run in milliseconds. */
  duration_ms?: number
  /** Short human-readable outcome metric, e.g. "47 blocks", "12 chunks". */
  metric?: string
  /** Error message shown when status is "error". */
  error?: string
}
