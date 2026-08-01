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
const ENCODE_NODE_ID = "encode";
const HYDRATE_NODE_ID = "hydrate";

const QUERY_FAMILY = "query";
const NORMALIZE_KIND = "normalize";
/** The mutually-exclusive query-transform kinds — `normalize` shares the `query` family but is NOT one. */
export const QUERY_TRANSFORM_KINDS = ["rewrite", "hyde"] as const;
export type QueryTransformKind = (typeof QUERY_TRANSFORM_KINDS)[number];
// The former `normalize.spec` consumers the transform's output spec is repointed onto (and back).
const SPEC_CONSUMER_IDS = [ENCODE_NODE_ID, RETRIEVE_NODE_ID, HYDRATE_NODE_ID];

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

/**
 * The active query-transform kind (`rewrite` | `hyde`), or null when none is spliced in.
 *
 * Looks for a `query`-family node that is NOT `normalize` — the toggle's single source of truth,
 * mirroring `isRerankEnabled`. Only one such node ever exists (the transforms are mutually exclusive).
 */
export function queryTransformKind(blob: GroupBlob): QueryTransformKind | null {
  const node = blob.nodes.find(
    (n): n is ActionBlob =>
      isActionBlob(n) &&
      n.family === QUERY_FAMILY &&
      n.kind !== NORMALIZE_KIND &&
      (QUERY_TRANSFORM_KINDS as readonly string[]).includes(n.kind),
  );
  return node ? (node.kind as QueryTransformKind) : null;
}

/** Repoints every present spec-consumer binding (encode/retrieve/hydrate) onto `sourceNodeId.spec`,
 *  preserving each entry's other slots. Rerank's own spec binding is deliberately left untouched. */
function repointSpecConsumers(bindings: GroupBlob["bindings"], sourceNodeId: string): GroupBlob["bindings"] {
  const next = { ...bindings };
  for (const id of SPEC_CONSUMER_IDS) {
    const entry = next[id];
    if (entry && "spec" in entry) next[id] = { ...entry, spec: nodeBinding(sourceNodeId, "spec") };
  }
  return next;
}

/**
 * Selects the query transform — `rewrite`, `hyde`, or `null` (off) — mutually exclusively.
 *
 * Always reverts any transform already present first (so the two kinds can never coexist), then
 * splices the requested one. A no-op when the requested kind already holds. Rerank nodes/bindings
 * are never touched, so a search with rerank enabled keeps it across a transform change. Every
 * lookup is by id or by (from, to) endpoints — array order is never assumed.
 */
export function setQueryTransform(blob: GroupBlob, kind: QueryTransformKind | null): GroupBlob {
  if (queryTransformKind(blob) === kind) return blob;
  const reverted = removeQueryTransform(blob);
  return kind ? insertQueryTransform(reverted, kind) : reverted;
}

function removeQueryTransform(blob: GroupBlob): GroupBlob {
  const qnode = queryTransformKind(blob);
  if (!qnode) return blob;

  // 1. Drop the transform node (its id equals its kind, matching the backend blob).
  const nodes = blob.nodes.filter((node) => !(isActionBlob(node) && node.id === qnode));

  // 2. Collapse normalize→qnode→encode back into a single normalize→encode.
  const transitions = [
    ...blob.transitions.filter(
      (t) =>
        !(t.from_node_id === NORMALIZE_NODE_ID && t.to_node_id === qnode) &&
        !(t.from_node_id === qnode && t.to_node_id === ENCODE_NODE_ID),
    ),
    onSuccess(NORMALIZE_NODE_ID, ENCODE_NODE_ID),
  ];

  // 3. Drop the transform's binding entry and repoint every spec consumer back onto normalize.
  const { [qnode]: _dropped, ...restBindings } = blob.bindings;
  const bindings = repointSpecConsumers(restBindings, NORMALIZE_NODE_ID);

  return { ...blob, nodes, transitions, bindings };
}

function insertQueryTransform(blob: GroupBlob, kind: QueryTransformKind): GroupBlob {
  // 1. Insert the transform node right after `normalize` (readability only — lookups never rely on
  //    it). Empty config → the backend fills the endpoint defaults; the user sets a real api_key.
  const normalizeIndex = blob.nodes.findIndex((node) => isActionBlob(node) && node.id === NORMALIZE_NODE_ID);
  const qNode: ActionBlob = { node_type: "action", id: kind, family: QUERY_FAMILY, kind, config: {} };
  const nodes =
    normalizeIndex === -1
      ? [...blob.nodes, qNode]
      : [...blob.nodes.slice(0, normalizeIndex + 1), qNode, ...blob.nodes.slice(normalizeIndex + 1)];

  // 2. Splice normalize→qnode→encode in place of normalize→encode.
  const transitions = [
    ...blob.transitions.filter(
      (t) => !(t.from_node_id === NORMALIZE_NODE_ID && t.to_node_id === ENCODE_NODE_ID),
    ),
    onSuccess(NORMALIZE_NODE_ID, kind),
    onSuccess(kind, ENCODE_NODE_ID),
  ];

  // 3. The transform reads normalize.spec; every downstream spec consumer is repointed onto its
  //    QuerySpec→QuerySpec output.
  const bindings = repointSpecConsumers(
    { ...blob.bindings, [kind]: { spec: nodeBinding(NORMALIZE_NODE_ID, "spec") } },
    kind,
  );

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
