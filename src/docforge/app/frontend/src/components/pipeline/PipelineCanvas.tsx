// ====== Code Summary ======
// PipelineCanvas — React Flow powered ingestion pipeline graph.
// Replaces the hand-built PipelineFlowGraph with a polished interactive canvas:
// S0→S6 stages as custom StageFlowNode cards, auto-positioned in a single
// horizontal row.  Smoothstep edges with arrowheads connect consecutive stages.
// Background dot grid, Controls, and MiniMap are all themed via CSS custom
// properties.  Selecting a node fires onStageClick in the parent.

// ====== Third-Party Library Imports ======
import { useCallback, useMemo } from 'react'
import {
  ReactFlow,
  Background,
  BackgroundVariant,
  Controls,
  MarkerType,
} from '@xyflow/react'
import type { Edge, Node, NodeMouseHandler } from '@xyflow/react'

// ====== Internal Project Imports ======
import type { ConfigState } from '../../api/types'
import { StageFlowNode } from './StageFlowNode'
import type { StageNodeData } from './StageFlowNode'
import type { StageDefinition, StageResult } from './types'

// ── Types ─────────────────────────────────────────────────────────────────────

interface PipelineCanvasProps {
  /** Ordered list of stage definitions to render as nodes. */
  stages: StageDefinition[]
  /** Rendering mode — "config" for pipeline setup, "trace" for post-run. */
  mode: 'config' | 'trace'
  /** Per-stage runtime results (trace mode only). */
  stageResults?: Record<string, StageResult>
  /** Id of the stage currently open in the detail panel. */
  activeStageId?: string | null
  /** Called when the user clicks a stage card. */
  onStageClick: (stage: StageDefinition) => void
  /** Live collection config used for provider summaries on each node. */
  configState?: ConfigState | null
}

// ── Constants ─────────────────────────────────────────────────────────────────

/** Horizontal distance (px) between the left edges of consecutive stage nodes. */
const NODE_SPACING_X = 240

/** Node width supplied to react-flow for edge routing before DOM measurement. */
const NODE_WIDTH = 175

/**
 * nodeTypes MUST be declared at module scope (stable reference) to prevent
 * react-flow from unmounting and remounting nodes on every parent re-render.
 */
const NODE_TYPES = { stageFlowNode: StageFlowNode } as const

// ── Component ─────────────────────────────────────────────────────────────────

/**
 * React Flow canvas for the S0→S6 ingestion pipeline.
 *
 * Auto-positions stages in a single horizontal row: node i sits at
 * x = i * NODE_SPACING_X, y = 0.  A smoothstep edge with an arrowhead marker
 * connects each consecutive pair.  fitView centers and scales the whole graph
 * into the canvas on mount and whenever stages change.
 *
 * Args:
 *   stages:        Ordered stage definitions (S0→S6).
 *   mode:          "config" or "trace" rendering context.
 *   stageResults:  Per-stage runtime results (trace mode only).
 *   activeStageId: Id of the stage whose detail panel is open.
 *   onStageClick:  Callback fired when the user clicks a stage node.
 *   configState:   Live config used to derive provider summaries on nodes.
 */
export function PipelineCanvas({
  stages,
  mode,
  stageResults,
  activeStageId,
  onStageClick,
  configState,
}: PipelineCanvasProps) {
  // 1. Build one node per stage, positioned in a single horizontal row.
  const nodes: Node<StageNodeData>[] = useMemo(
    () =>
      stages.map((stage, index) => ({
        id:       stage.id,
        type:     'stageFlowNode',
        position: { x: index * NODE_SPACING_X, y: 0 },
        width:    NODE_WIDTH,
        data: {
          stage,
          mode,
          result:      stageResults?.[stage.id],
          isActive:    activeStageId === stage.id,
          configState: configState ?? null,
        },
        draggable: false,
        selectable: false,
      })),
    [stages, mode, stageResults, activeStageId, configState],
  )

  // 2. Build one smoothstep edge between each consecutive stage pair.
  const edges: Edge[] = useMemo(
    () =>
      stages.slice(0, -1).map((stage, i) => ({
        id:     `e-${stage.id}-${stages[i + 1].id}`,
        source: stage.id,
        target: stages[i + 1].id,
        type:   'smoothstep',
        style:  { stroke: 'var(--border-strong)', strokeWidth: 1.5 },
        markerEnd: {
          type:   MarkerType.ArrowClosed,
          color:  'var(--border-strong)',
          width:  14,
          height: 14,
        },
      })),
    [stages],
  )

  // 3. Map react-flow node click events to the stage-click handler.
  const handleNodeClick: NodeMouseHandler = useCallback(
    (_event, node) => {
      const { stage } = node.data as StageNodeData
      onStageClick(stage)
    },
    [onStageClick],
  )

  return (
    <div className="pipeline-canvas">
      {/* Mode badge — floats above the canvas, top-right. */}
      <span className="pipeline-canvas-badge" aria-label={`Mode: ${mode}`}>
        {mode === 'config' ? 'CONFIG' : 'TRACE'}
      </span>

      <ReactFlow
        nodes={nodes}
        edges={edges}
        nodeTypes={NODE_TYPES}
        onNodeClick={handleNodeClick}
        colorMode="dark"
        fitView
        fitViewOptions={{ padding: 0.28, maxZoom: 1.1 }}
        minZoom={0.3}
        maxZoom={2}
        nodesDraggable={false}
        nodesConnectable={false}
        elementsSelectable={false}
        panOnDrag
        zoomOnScroll={false}
        zoomOnPinch
        zoomOnDoubleClick={false}
        proOptions={{ hideAttribution: true }}
      >
        {/* Subtle dot grid — color drives the dot fill via the `color` prop. */}
        <Background
          variant={BackgroundVariant.Dots}
          gap={20}
          size={1}
          color="var(--border)"
          style={{ opacity: 0.45 }}
        />

        {/* Zoom/fit controls — themed via .pipeline-canvas .react-flow__controls.
            No MiniMap: the pipeline is a short linear S0→S6 chain, so a minimap adds
            no navigation value and only crowds the canvas. */}
        <Controls showInteractive={false} position="bottom-right" />
      </ReactFlow>
    </div>
  )
}
