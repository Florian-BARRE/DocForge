// ====== Code Summary ======
// Pure blob edits for the search pipeline editor. The search graph has a FIXED, flat topology
// (no stage compiler, no cascades to heal) — editing a node's config is a plain immutable replace
// of that one node in the top-level `nodes` array, nothing more.

import type { ActionBlob, GroupBlob, NodeBlob } from "../../../api/types";

/** True for the only node shape the search graph's default topology ever produces today. */
export function isActionBlob(node: NodeBlob): node is ActionBlob {
  return node.node_type === "action";
}

/** Replaces one field of one node's config, leaving every other node untouched. */
export function setNodeConfigField(blob: GroupBlob, nodeId: string, field: string, value: unknown): GroupBlob {
  return {
    ...blob,
    nodes: blob.nodes.map((node) =>
      isActionBlob(node) && node.id === nodeId
        ? { ...node, config: { ...node.config, [field]: value } }
        : node,
    ),
  };
}
