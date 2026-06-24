// ====== Code Summary ======
// <DynamicFieldsGroup> — render a set of nested DynamicField overlays whose
// field_paths share a common prefix (e.g. `pipeline.` or `patch.pipeline.`).
//
// Overlays are grouped by their first segment after the prefix (so for pipeline
// overlays, this becomes per-stage: parse / enrich / chunk / embed).  Each overlay
// then renders via <ChoicePicker>; values are read/written into the host's body
// via a single nested-path setter, so the host only owns the top-level body state.

import { useMemo } from 'react'
import type { DiscoveryResponse, DynamicField } from '../../api/types'
import { ChoicePicker } from './ChoicePicker'

interface Props {
  // All dynamic fields from `endpoint.dynamic_fields`.
  fields: DynamicField[]
  // Prefix to filter on (e.g. `pipeline` for create_collection; `patch.pipeline` for update_config).
  // Empty string filters in everything.
  prefix?: string
  // Controlled state for the value AT prefix (i.e. body[prefix...] or body when prefix is "").
  value: Record<string, unknown>
  onChange: (v: Record<string, unknown>) => void
  // Presentation: human label per group key (e.g. {parse: 'S1 · Parse'}).
  groupLabels?: Record<string, string>
  // Presentation: preferred group ordering (unknown groups go after, in discovery order).
  groupOrder?: string[]
  // Forwarded so nested provider pickers (semantic.embed) can resolve their choices.
  discovery?: DiscoveryResponse
}

export function DynamicFieldsGroup({
  fields, prefix = '', value, onChange, groupLabels = {}, groupOrder = [], discovery,
}: Props) {
  // 1. Normalise the prefix and pre-strip it from each field path so subsequent
  // grouping/setting logic works against the "post-prefix" path.
  const prefixDot = prefix ? `${prefix}.` : ''

  const scoped = useMemo(() => {
    return fields
      .filter(df => prefix === '' || df.field_path.startsWith(prefixDot))
      .map(df => ({
        ...df,
        // Path relative to the prefix root (e.g. "enrich.chart_to_data").
        field_path: prefix === '' ? df.field_path : df.field_path.slice(prefixDot.length),
      }))
  }, [fields, prefix, prefixDot])

  // 2. Group overlays by first segment.  Single-segment paths (rare for pipeline,
  // common for top-level overlays like "filters") land in the ungrouped bucket.
  const { groups, orderedKeys } = useMemo(() => {
    const groups: Record<string, DynamicField[]> = {}
    const seen: string[] = []
    for (const df of scoped) {
      const seg = df.field_path.includes('.') ? df.field_path.split('.')[0] : ''
      if (!(seg in groups)) { groups[seg] = []; seen.push(seg) }
      groups[seg].push(df)
    }
    // Preferred order first (only those actually present), then discovery order for the rest.
    const known = groupOrder.filter(g => g in groups)
    const extra = seen.filter(g => !known.includes(g))
    return { groups, orderedKeys: [...known, ...extra] }
  }, [scoped, groupOrder])

  // 3. Read / write into the nested body shape via dot path.
  function readPath(path: string): unknown {
    if (!path) return value
    const keys = path.split('.')
    let cursor: unknown = value
    for (const k of keys) {
      if (cursor && typeof cursor === 'object') cursor = (cursor as Record<string, unknown>)[k]
      else return undefined
    }
    return cursor
  }

  function setPath(path: string, v: unknown) {
    if (!path) return
    const keys = path.split('.')
    const next = { ...value }
    let cursor: Record<string, unknown> = next
    for (let i = 0; i < keys.length - 1; i++) {
      const k = keys[i]
      cursor[k] = { ...(cursor[k] as Record<string, unknown> ?? {}) }
      cursor = cursor[k] as Record<string, unknown>
    }
    cursor[keys[keys.length - 1]] = v
    onChange(next)
  }

  if (scoped.length === 0) return null

  return (
    <div className="dyn-group">
      {orderedKeys.map(groupKey => {
        const items = groups[groupKey]
        if (!items?.length) return null
        return (
          <div key={groupKey || '_ungrouped'} className="config-stage-section">
            {groupKey && (
              <div className="config-stage-label">
                {groupLabels[groupKey] ?? humanize(groupKey)}
              </div>
            )}
            {items.map(df => (
              <ChoicePicker
                key={df.field_path}
                field={df}
                value={readPath(df.field_path)}
                onChange={v => setPath(df.field_path, v)}
                discovery={discovery}
              />
            ))}
          </div>
        )
      })}
    </div>
  )
}

function humanize(s: string): string {
  return s.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase())
}
