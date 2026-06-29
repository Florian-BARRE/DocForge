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
// Gate pairing (GENERIC — driven purely by path suffixes, no stage hardcoding):
//   A chain at "…X_chain"  pairs with a sibling object at "…X_gate".
//   A chain at "…chain"    pairs with a sibling object at "…gate".
//   ALL chain+gate pairs at a given level are detected and rendered as independent
//   ChainLadder instances (handles Enrich: classifier_chain/gate, ocr_chain/gate,
//   vlm_chain/gate).  A chain without a matching gate, or a gate without a chain,
//   still renders — nothing is dropped.
//   A consumed gate NEVER renders standalone (no duplication).
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
import { ObjectListPicker } from './pickers/ObjectListPicker'
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
  const seg = node.path.split('.').pop() ?? node.path
  // Use the backend label if provided; otherwise humanize the raw key.
  // In both cases, apply acronym post-processing so that words like "url"
  // and "api" are uppercased regardless of the source (backend may title-case
  // without knowing they are acronyms, e.g. "Base Url" → "Base URL").
  const rawLabel = node.label || humanize(seg)
  const label = rawLabel.replace(/\b\w+/g, word =>
    ACRONYMS.has(word.toLowerCase()) ? word.toUpperCase() : word
  )
  return {
    name: seg,
    type: node.type ?? 'str',
    label,
    default: node.default,
    description: node.description,
    min: node.min ?? undefined,
    max: node.max ?? undefined,
    enum: node.options ?? undefined,
  }
}

/**
 * Common abbreviations that should always be fully uppercased.
 * Keeps "Base URL", "API Key", "OCR" etc. readable in field labels.
 */
const ACRONYMS = new Set(['url', 'api', 'id', 'ocr', 'vlm', 'llm', 'http', 'ssl', 'jwt'])

/**
 * Humanize a snake_case path segment for display as a field or section label.
 *
 * Converts underscores to spaces, title-cases words, and fully uppercases known
 * abbreviations so that "base_url" → "Base URL" and "api_key" → "API Key".
 *
 * Args:
 *   seg: Raw snake_case segment (e.g. "base_url", "split_method").
 *
 * Returns:
 *   string: Human-readable label (e.g. "Base URL", "Split Method").
 */
function humanize(seg: string): string {
  return seg
    .replace(/_/g, ' ')
    .replace(/\b\w+/g, word =>
      ACRONYMS.has(word.toLowerCase())
        ? word.toUpperCase()
        : word.charAt(0).toUpperCase() + word.slice(1)
    )
}

// ── Helpers ── Chain pairing ──────────────────────────────────────────────────

/**
 * Derive the expected gate path segment for a given chain path segment.
 *
 * Pairing rule (pure path suffix — no stage-name hardcoding):
 *   "X_chain"  →  "X_gate"   (e.g., "classifier_chain" → "classifier_gate")
 *   "chain"    →  "gate"     (e.g., plain chain → plain gate)
 *   anything else → null (no gate pair)
 *
 * Args:
 *   chainSeg: Last path segment of the chain node.
 *
 * Returns:
 *   string | null: Expected gate segment, or null if no pairing applies.
 */
function gateSiblingSegFor(chainSeg: string): string | null {
  if (chainSeg === 'chain') return 'gate'
  if (chainSeg.endsWith('_chain')) return chainSeg.slice(0, -'_chain'.length) + '_gate'
  return null
}

/**
 * Derive a human-readable group title from a chain ConfigNode.
 *
 * Priority order:
 *   1. node.capability (e.g., "ocr" → "OCR", "parser" → "Parser")
 *   2. node.label with trailing " Chain" stripped
 *   3. Humanized last path segment with "_chain" removed
 *
 * Args:
 *   chain: The chain ConfigNode.
 *
 * Returns:
 *   string: Title like "Classifier", "OCR", "VLM", "Parser", "Embed".
 */
function chainGroupTitle(chain: ConfigNode): string {
  // 1. Capability is the most reliable source (backed by the provider registry).
  if (chain.capability) {
    const cap = chain.capability
    return ACRONYMS.has(cap.toLowerCase())
      ? cap.toUpperCase()
      : cap.charAt(0).toUpperCase() + cap.slice(1)
  }
  // 2. Label from the discovery backend, stripping the trailing "Chain" word.
  if (chain.label) {
    const stripped = chain.label.replace(/\s*[Cc]hain$/, '').trim()
    if (stripped) return stripped
  }
  // 3. Humanize the path segment without the "_chain" suffix.
  const seg = (chain.path.split('.').pop() ?? chain.path).replace(/_chain$/, '')
  return humanize(seg)
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

  // ── Multi-chain + gate pairing (GENERIC, path-suffix driven) ──────────────
  //
  // For every chain node in this sibling list, look for a matching gate object
  // using the path-suffix rule in gateSiblingSegFor().  Consumed gates are
  // tracked in a Set so they are excluded from the `otherNodes` fallthrough
  // render — avoiding both "dropped nodes" and "duplicated standalone gates".
  const chainNodes = nodes.filter(n => n.kind === 'chain')
  const consumedGates = new Set<ConfigNode>()

  interface ChainGatePair {
    chain: ConfigNode
    gate: ConfigNode | null
  }

  const pairs: ChainGatePair[] = chainNodes.map(chain => {
    const chainSeg = chain.path.split('.').pop() ?? ''
    const expectedGateSeg = gateSiblingSegFor(chainSeg)
    const gate = expectedGateSeg
      ? nodes.find(n => n.kind === 'object' && (n.path.split('.').pop() ?? '') === expectedGateSeg)
      : undefined
    if (gate) consumedGates.add(gate)
    return { chain, gate: gate ?? null }
  })

  // Nodes that are not chains and not consumed by a pairing — rendered normally.
  const chainSet = new Set<ConfigNode>(chainNodes)
  const otherNodes = nodes.filter(n => !chainSet.has(n) && !consumedGates.has(n))

  // Show group titles when there are multiple chain groups (e.g., Enrich stage).
  // For a single chain the title is optional but still provides context.
  const showTitles = pairs.length > 1

  return (
    <>
      {/* Render all chain+gate pairs as ChainLadder instances */}
      {pairs.map(({ chain, gate }) => (
        <ChainLadder
          key={chain.path}
          node={chain}
          gateNode={gate}
          groupTitle={showTitles ? chainGroupTitle(chain) : undefined}
          value={readValue(chain.path) as Array<{ id: string; [k: string]: unknown }> | undefined}
          onChange={v => writeValue(chain.path, v)}
          readValue={readValue}
          writeValue={writeValue}
          renderChildren={renderChildren}
        />
      ))}

      {/* Remaining nodes (scalars, enums, objects, provider_unions) */}
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
              showHint
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
              showHint
            />
          )
        }

        // ── object ──────────────────────────────────────────────────────────
        // Renders as a labeled section that recurses its children.
        // A gate object consumed by a chain+gate pair never reaches here.
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

        // ── object_list ─────────────────────────────────────────────────
        // Generic repeater for list[model] nodes (e.g., pipeline.metagen.targets).
        // Each item recurses node.item_schema via the renderChildren render-prop.
        // GENERIC — never special-cases the model name or field names.
        if (node.kind === 'object_list') {
          return (
            <ObjectListPicker
              key={key}
              node={node}
              value={readValue(node.path) as Record<string, unknown>[] | undefined}
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
