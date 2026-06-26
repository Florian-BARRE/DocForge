---
name: react-flow-canvas
description: PipelineCanvas react-flow architecture — how the ingestion pipeline graph is built, themed, and wired (R2, 2026-06-26)
metadata:
  type: project
---

## React Flow canvas — ingestion pipeline (R2)

`@xyflow/react` v12.11.1 added to `package.json` dependencies.
Stylesheet imported in `main.tsx` before `global.css` so our tokens override it:
`import '@xyflow/react/dist/style.css'`

### Component tree

- `PipelineCanvas.tsx` — the ReactFlow wrapper (replaces `PipelineFlowGraph`)
  - Positions stages in a single horizontal row: `x = index * 240, y = 0`
  - NODE_TYPES declared at module scope (stable ref — prevents remount on re-render)
  - `elementsSelectable={false}`, `nodesDraggable={false}`, `nodesConnectable={false}`
  - `zoomOnScroll={false}` — prevents zooming on page scroll
  - `onNodeClick` fires → reads `node.data as StageNodeData` → calls `onStageClick(stage)`
  - Includes `<Background variant=Dots>`, `<Controls>`, `<MiniMap>` all themed via CSS
  - Mode badge (CONFIG/TRACE) is an absolutely-positioned span ABOVE the ReactFlow div

- `StageFlowNode.tsx` — react-flow custom node type (full rewrite of old hand-built card)
  - Exports `StageNodeData` (extends `Record<string, unknown>` for react-flow generic constraint)
  - Exports `StageFlowNodeType = Node<StageNodeData>` 
  - Receives `NodeProps<StageFlowNodeType>` — casts `data` field to `StageNodeData`
  - Renders: accent strip (3px, per-stage CSS var reference) | ID badge | icon | label | desc | footer
  - Footer: provider chip + ON/OPT-IN pill (config) or trace status + duration (trace)
  - Left Handle (target) + Right Handle (source), styled via `.sfn-handle` class as 8px dots

### Dead files (stubs — safe to delete)

- `PipelineFlowGraph.tsx` → `export {}` (was only imported by PipelineTab, now replaced)
- `StageConnector.tsx` → `export {}` (was only imported by PipelineFlowGraph)

### Preserved

- `PipelineGraph.tsx` + `StageNode.tsx` — still used by `SearchTab.tsx` (UNTOUCHED)
- `StageConfigPanel.tsx`, `ConfigSaveBar.tsx`, `ConfigHistoryPanel.tsx` — all unchanged
- `ChainLadder.tsx`, `ChainGateDisplay.tsx`, `ProviderCard.tsx` — all unchanged

### Token theming

All react-flow overrides scoped to `.pipeline-canvas` in `global.css`:
- `.pipeline-canvas .react-flow { background: transparent }` — canvas BG via wrapper
- `.pipeline-canvas .react-flow__controls-button` — dark surface + muted color
- `.pipeline-canvas .react-flow__minimap` — dark surface background
- `.pipeline-canvas .react-flow__edge-path` — `var(--border-strong)` stroke
- `.sfn-handle` — 8px dots: `background: var(--border-strong)`, border: `var(--surface)`
- Accent strip uses inline `style={{ background: accentColor }}` where accentColor is a
  CSS var reference string like `'var(--accent)'` or `'var(--s-done)'` — no hex values

Per-stage accent colors (all CSS var refs, not hex):
- s0/transform: `var(--s-info)` (blue)
- s1/s6/rerank: `var(--accent)` (indigo)
- s2: `var(--s-warning)` (amber)
- s4/retrieve: `var(--s-done)` (emerald)
- s5: `var(--s-info)`

### Build

`npm run build` (tsc + vite) passes cleanly. 300 modules, bundle 512KB (expected — react-flow is large).
The 512KB size warning is cosmetic — not a build failure.

**Why:** react-flow nodes require `data` to extend `Record<string, unknown>`. Interface with explicit
`extends Record<string, unknown>` satisfies the generic constraint. Using `NodeProps` (without generic)
and casting `data` inside avoids TypeScript gymnastics at the nodeTypes registration site.
