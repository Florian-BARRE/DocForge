// ====== Code Summary ======
// ResourcesPanel — displays app-side device capabilities, GPU info, and
// admission limits from GET /api/v1/monitoring/resources.
// Renders a 2-column capability matrix and a limits summary block.

import type { MonitoringResourcesResponse, CapabilityDevice } from '../../api/types'
import { SectionHeader } from '../ui/primitives/SectionHeader'
import { Tag } from '../ui/primitives/Tag'
import type { TagVariant } from '../ui/primitives/Tag'
import { EmptyState } from '../ui/primitives/EmptyState'

// ── Types ────────────────────────────────────────────────────────────────────

interface ResourcesPanelProps {
  /** Latest resources snapshot, or null while loading. */
  resources: MonitoringResourcesResponse | null
}

// ── Constants ─────────────────────────────────────────────────────────────────

const CAPABILITIES: Array<{ key: keyof MonitoringResourcesResponse['device']['capabilities']; label: string }> = [
  { key: 'parse',    label: 'Parse'    },
  { key: 'ocr',     label: 'OCR'      },
  { key: 'vlm',     label: 'VLM'      },
  { key: 'embed',   label: 'Embed'    },
  { key: 'rerank',  label: 'Rerank'   },
  { key: 'classify',label: 'Classify' },
]

// ── Helpers ───────────────────────────────────────────────────────────────────

function deviceVariant(device: CapabilityDevice): TagVariant {
  if (device === 'gpu')    return 'accent'
  if (device === 'remote') return 'warning'
  return 'default'
}

function limitLabel(value: number): string {
  return value === 0 ? '∞ unlimited' : String(value)
}

// ── Component ────────────────────────────────────────────────────────────────

/**
 * Device capabilities matrix and admission limits panel.
 *
 * Shows:
 *   - A 2-column grid of capability rows (parse/ocr/vlm/embed/rerank/classify)
 *     with cpu/gpu/remote tags.
 *   - GPU availability, name, and CUDA version (when gpu_available is true).
 *   - Admission gate settings (enabled, max_queue_depth, max_in_flight_global).
 *
 * Args:
 *   resources: Snapshot from GET /monitoring/resources.
 */
export function ResourcesPanel({ resources }: ResourcesPanelProps) {
  if (!resources) {
    return (
      <div>
        <SectionHeader>Resources</SectionHeader>
        <EmptyState message="Loading resources…" />
      </div>
    )
  }

  const { device, limits } = resources

  return (
    <div>
      <SectionHeader>Resources</SectionHeader>

      {/* ── Capability matrix ── */}
      <div style={{
        display: 'grid',
        gridTemplateColumns: '1fr 1fr',
        gap: '5px 12px',
        marginBottom: 14,
      }}>
        {CAPABILITIES.map(cap => {
          const resolved = device.capabilities[cap.key]
          return (
            <div key={cap.key} style={{
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              padding: '5px 8px',
              background: 'var(--surface-raised)',
              borderRadius: 'var(--radius-sm)',
              border: '1px solid var(--border)',
            }}>
              <span style={{ fontSize: 11, color: 'var(--text-muted)' }}>{cap.label}</span>
              <Tag variant={deviceVariant(resolved)} style={{ fontSize: 10 }}>
                {resolved}
              </Tag>
            </div>
          )
        })}
      </div>

      {/* ── GPU info ── */}
      <div style={{ marginBottom: 14 }}>
        <span className="section-title" style={{ display: 'block', marginBottom: 6 }}>GPU</span>
        {device.gpu_available ? (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 3, fontSize: 12 }}>
            <Row label="Name"   value={device.gpu_name     ?? '—'} />
            <Row label="CUDA"   value={device.cuda_version  ?? '—'} />
          </div>
        ) : (
          <span style={{ fontSize: 12, color: 'var(--text-dim)' }}>
            GPU not available on app host — GPU metrics are from worker heartbeats above.
          </span>
        )}
      </div>

      {/* ── Admission limits ── */}
      <div>
        <span className="section-title" style={{ display: 'block', marginBottom: 6 }}>Admission gate</span>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 3, fontSize: 12 }}>
          <Row
            label="Enabled"
            value={limits.enabled ? 'Yes' : 'Disabled'}
            color={limits.enabled ? 'var(--s-done)' : 'var(--text-dim)'}
          />
          <Row label="Max queue depth"  value={limitLabel(limits.max_queue_depth)} />
          <Row label="Max in-flight"    value={limitLabel(limits.max_in_flight_global)} />
        </div>
      </div>
    </div>
  )
}

// ── Row sub-component ──────────────────────────────────────────────────────────

function Row({ label, value, color }: { label: string; value: string; color?: string }) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 8 }}>
      <span style={{ color: 'var(--text-dim)', fontSize: 11 }}>{label}</span>
      <span style={{ color: color ?? 'var(--text-muted)', fontSize: 11, fontFamily: 'var(--font-mono)' }}>
        {value}
      </span>
    </div>
  )
}
