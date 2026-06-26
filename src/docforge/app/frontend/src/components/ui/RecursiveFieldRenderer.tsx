// ====== Code Summary ======
// RecursiveFieldRenderer — generic renderer for a ConfigNode[] tree emitted by
// the backend's `config_tree` discovery endpoint.
//
// Dispatches each node by `kind`:
//   scalar         -> FieldInput (reuses type/min/max/default)
//   enum           -> FieldInput with options array (select)
//   object         -> collapsible section header + recurse children
//   provider_union -> ProviderUnionPicker (chip group; nested unions handled uniformly)
//   chain          -> ChainLadder (expressive fallback ladder + gate connector)
//
// Special grouping: when a sibling list contains a `chain` node AND an `object`
// node whose last path segment is "gate", they are co-rendered via ChainLadder so
// gate settings appear as an editable section alongside the provider ladder.
//
// Read/write accessors use absolute node.path strings and are provided by the
// caller (StageConfigPanel or a parent picker) via `readValue`/`writeValue` props.
// This design avoids a shared mutable state — each call site owns its value object.
//
// The render-prop pattern (renderChildren passed to pickers) breaks the apparent
// circular dependency: RecursiveFieldRenderer -> pickers -> RecursiveFieldRenderer.
// No lazy(), no Suspense, no circular module graph.

// ====== Internal Project Imports ======
import type { ConfigNode } from '../../api/types'
import { FieldInput } from './FieldInput'
import type { ParamSchema } from '../../api/types'
import { ChainLadder } from '../pipeline/ChainLadder'
import { ProviderUnionPicker } from './pickers/ProviderUnionPicker'

// ── Helpers ───────────────────────────────────────────────────────────────────

/**
 * Convert a ConfigNode (scalar or enum kind) to a ParamSchema so FieldInput
 * can render it without modification.
 *
 * Args:
 *   node: Scalar or enum ConfigNode.
 *
 * Returns:
 *   ParamSchema: Compatible schema for FieldInput.
 */
function nodeToParamSchema(node: ConfigNode): ParamSchema {
  return {
    name: node.path.split('.').pop() ?? node.path,
    type: node.type ?? 'str',
    label: node.label || (node.path.split('.').pop() ?? node.path),
    default: node.default,
    description: node.description,
    min: node.min ?? undefined,
    max: node.max ?? undefined,
    enum: node.options ?? undefined,
  }
}

/**
 * Humanize a path segment for display as a section label.
 *
 * Args:
 *   seg: Raw segment string (e.g. "split_method").
 *
 * Returns:
 *   string: Title-cased label (e.g. "Split Method").
 */
function humanize(seg: string): string {
  return seg.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase())
}

// ── Component ─────────────────────────────────────────────────────────────────

/**
 * Recursive config tree renderer driven by ConfigNode descriptors.
 *
 * Called by StageConfigPanel to render the config subtree for one pipeline stage.
 * Also injected as `renderChildren` into ProviderUnionPicker and ChainLadder so
 * nested provider params (including nested provider_unions like semantic.embed)
 * render uniformly without any hand-coded field mapping.
 *
 * The `readValue`/`writeValue` pair is always defined by the caller with the
 * absolute node.path string as the key. StageConfigPanel provides accessors
 * against its local `value` draft; pickers provide accessors against their
 * flat entry object.
 *
 * Args:
 *   nodes:      List of ConfigNode siblings to render.
 *   readValue:  Return the current value for a given absolute path string.
 *   writeValue: Persist a value change for a given absolute path string.
 */
export function RecursiveFieldRenderer({
  nodes,
  readValue,
  writeValue,
}: {
  nodes: ConfigNode[]
  readValue: (absPath: string) => unknown
  writeValue: (absPath: string, v: unknown) => void
}) {
  // Build the render-prop function once so it can be passed to pickers.
  // This is the function that pickers call to render their own children.
  function renderChildren(
    childNodes: ConfigNode[],
    childRead: (absPath: string) => unknown,
    childWrite: (absPath: string, v: unknown) => void,
  ) {
    return (
      <RecursiveFieldRenderer
        nodes={childNodes}
        readValue={childRead}
        writeValue={childWrite}
      />
    )
  }

  // Detect chain + gate sibling pair at this level so they can be co-rendered
  // as a ChainLadder rather than a generic chain list + standalone gate form.
  // Gate detection: kind=object whose path segment ends with "gate".
  const chainNode = nodes.find(n => n.kind === 'chain')
  const gateNode  = chainNode
    ? nodes.find(n => n.kind === 'object' && n.path.split('.').pop() === 'gate')
    : undefined

  // Nodes that are neither the chain nor its gate sibling render normally.
  const otherNodes = chainNode
    ? nodes.filter(n => n !== chainNode && n !== gateNode)
    : nodes

  return (
    <>
      {/* Co-render chain + gate as ChainLadder when present */}
      {chainNode && (
        <ChainLadder
          key={chainNode.path}
          node={chainNode}
          gateNode={gateNode ?? null}
          value={readValue(chainNode.path) as Array<{ id: string; [k: string]: unknown }> | undefined}
          onChange={v => writeValue(chainNode.path, v)}
          readValue={readValue}
          writeValue={writeValue}
          renderChildren={renderChildren}
        />
      )}

      {/* Remaining nodes rendered with the standard dispatch */}
      {otherNodes.map(node => {
        const key = node.path

        // ── scalar ──────────────────────────────────────────────────────────
        if (node.kind === 'scalar') {
          return (
            <FieldInput
              key={key}
              schema={nodeToParamSchema(node)}
              value={readValue(node.path)}
              onChange={v => writeValue(node.path, v)}
            />
          )
        }

        // ── enum ────────────────────────────────────────────────────────────
        if (node.kind === 'enum') {
          return (
            <FieldInput
              key={key}
              schema={nodeToParamSchema(node)}
              value={readValue(node.path)}
              onChange={v => writeValue(node.path, v)}
            />
          )
        }

        // ── object ──────────────────────────────────────────────────────────
        // Renders as a collapsible section with the node.label as header.
        if (node.kind === 'object') {
          const children = node.children ?? []
          if (children.length === 0) return null
          const seg = node.path.split('.').pop() ?? node.path
          const sectionLabel = node.label || humanize(seg)

          // Pass through read/write unchanged — child node paths are absolute.
          return (
            <div key={key} className="config-stage-section">
              <div className="config-stage-label">{sectionLabel}</div>
              <RecursiveFieldRenderer
                nodes={children}
                readValue={readValue}
                writeValue={writeValue}
              />
            </div>
          )
        }

        // ── provider_union ─────────────────────────────────────────────────
        // Single-choice picker; nested provider sub-configs recurse via render-prop.
        if (node.kind === 'provider_union') {
          const currentVal = readValue(node.path)
          return (
            <ProviderUnionPicker
              key={key}
              node={node}
              value={currentVal as Record<string, unknown> | null | undefined}
              onChange={v => writeValue(node.path, v)}
              renderChildren={renderChildren}
            />
          )
        }

        return null
      })}
    </>
  )
}
