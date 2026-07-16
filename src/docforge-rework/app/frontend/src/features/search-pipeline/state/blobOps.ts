// ====== Code Summary ======
// Pure blob edits for the search pipeline editor. The search graph has a FIXED, flat topology
// (no stage compiler, no cascades to heal) — editing a node's config is a plain immutable replace
// of that one node in the top-level `nodes` array, nothing more. The rerank toggle is the one
// exception with real topology: it swaps between the two canonical shapes the backend's
// `SearchPipeline.default_blob()` / `rerank_blob()` produce (see search-pipeline/pipeline.py) —
// implemented here, not server-side, since the search graph has no `/stages/apply` to lean on.

import type { ActionBlob, Binding, GroupBlob, NodeBlob, Transition } from "../../../api/types";

const RERANK_NODE_ID = "rerank";
const RETRIEVE_NODE_ID = "retrieve";
const NORMALIZE_NODE_ID = "normalize";
const HYDRATE_NODE_ID = "hydrate";

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

function nodeBinding(nodeId: string, fieldName: string): Binding {
  return { source: "node", node_id: nodeId, field_name: fieldName };
}

function onSuccess(fromNodeId: string, toNodeId: string): Transition {
  return { from_node_id: fromNodeId, to_node_id: toNodeId, condition: { kind: "on_success" } };
}

/** True iff the blob's `rerank` cross-encoder node is present — the toggle's single source of truth. */
export function isRerankEnabled(blob: GroupBlob): boolean {
  return blob.nodes.some((node) => isActionBlob(node) && node.family === "rerank");
}

/**
 * Sets the rerank stage on or off, mirroring the backend's `rerank_blob()` topology exactly.
 *
 * A no-op (returns an equivalent blob) when the requested state already holds — enabling twice or
 * disabling twice never duplicates/re-removes anything. Node/transition order in the source arrays
 * is never assumed; every lookup is by id or by (from, to) endpoints.
 */
export function setRerankEnabled(blob: GroupBlob, enabled: boolean): GroupBlob {
  return enabled ? enableRerank(blob) : disableRerank(blob);
}

function enableRerank(blob: GroupBlob): GroupBlob {
  if (isRerankEnabled(blob)) return blob;

  // 1. Insert the rerank node right after `retrieve` (readability only — lookups never rely on it).
  const retrieveIndex = blob.nodes.findIndex((node) => isActionBlob(node) && node.id === RETRIEVE_NODE_ID);
  const rerankNode: ActionBlob = { node_type: "action", id: RERANK_NODE_ID, family: "rerank", kind: "cross_encoder", config: {} };
  const nodes =
    retrieveIndex === -1
      ? [...blob.nodes, rerankNode]
      : [...blob.nodes.slice(0, retrieveIndex + 1), rerankNode, ...blob.nodes.slice(retrieveIndex + 1)];

  // 2. Splice retrieve→rerank→hydrate in place of retrieve→hydrate.
  const transitions = [
    ...blob.transitions.filter(
      (t) => !(t.from_node_id === RETRIEVE_NODE_ID && t.to_node_id === HYDRATE_NODE_ID),
    ),
    onSuccess(RETRIEVE_NODE_ID, RERANK_NODE_ID),
    onSuccess(RERANK_NODE_ID, HYDRATE_NODE_ID),
  ];

  // 3. Wire the rerank node's inputs and rebind hydrate.candidates onto its output.
  const bindings: GroupBlob["bindings"] = {
    ...blob.bindings,
    [RERANK_NODE_ID]: {
      candidates: nodeBinding(RETRIEVE_NODE_ID, "candidates"),
      spec: nodeBinding(NORMALIZE_NODE_ID, "spec"),
    },
    [HYDRATE_NODE_ID]: {
      ...blob.bindings[HYDRATE_NODE_ID],
      candidates: nodeBinding(RERANK_NODE_ID, "candidates"),
    },
  };

  return { ...blob, nodes, transitions, bindings };
}

function disableRerank(blob: GroupBlob): GroupBlob {
  if (!isRerankEnabled(blob)) return blob;

  // 1. Drop the rerank node.
  const nodes = blob.nodes.filter((node) => !(isActionBlob(node) && node.id === RERANK_NODE_ID));

  // 2. Collapse retrieve→rerank→hydrate back into a single retrieve→hydrate.
  const transitions = [
    ...blob.transitions.filter(
      (t) =>
        !(t.from_node_id === RETRIEVE_NODE_ID && t.to_node_id === RERANK_NODE_ID) &&
        !(t.from_node_id === RERANK_NODE_ID && t.to_node_id === HYDRATE_NODE_ID),
    ),
    onSuccess(RETRIEVE_NODE_ID, HYDRATE_NODE_ID),
  ];

  // 3. Drop the rerank binding entry and rebind hydrate.candidates back onto retrieve.
  const { [RERANK_NODE_ID]: _dropped, ...restBindings } = blob.bindings;
  const bindings: GroupBlob["bindings"] = {
    ...restBindings,
    [HYDRATE_NODE_ID]: {
      ...blob.bindings[HYDRATE_NODE_ID],
      candidates: nodeBinding(RETRIEVE_NODE_ID, "candidates"),
    },
  };

  return { ...blob, nodes, transitions, bindings };
}
