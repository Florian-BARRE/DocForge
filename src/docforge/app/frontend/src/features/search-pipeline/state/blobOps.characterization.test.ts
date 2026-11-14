// ====== Code Summary ======
// Characterization (safety net) of search-pipeline/state/blobOps.ts: records TODAY's pure blob edits
// (node config replace, rerank toggle, rewrite/hyde transform select) as input -> output goldens so
// the big-component split (R-33) cannot change what the search pipeline editor sends. Pins the exact
// topology (node order, transitions, bindings) and the idempotence / immutability of every op.

// ====== Third-Party Library Imports ======
import { describe, expect, it } from "vitest";

// ====== Local Project Imports ======
import type { Binding, GroupBlob, NodeBlob } from "../../../api/types";
import {
  isActionBlob,
  isRerankEnabled,
  queryTransformKind,
  setNodeConfigField,
  setQueryTransform,
  setRerankEnabled,
} from "./blobOps";

function node(id: string, family: string, kind: string, config: Record<string, unknown> = {}): NodeBlob {
  return { node_type: "action", id, family, kind, config };
}

function ref(nodeId: string, field: string): Binding {
  return { source: "node", node_id: nodeId, field_name: field };
}

function ok(from: string, to: string) {
  return { from_node_id: from, to_node_id: to, condition: { kind: "on_success" } };
}

/** The search graph's default topology: normalize -> encode -> retrieve -> hydrate. */
function defaultBlob(): GroupBlob {
  return {
    node_type: "group",
    id: "search",
    nodes: [
      node("normalize", "query", "normalize", { lowercase: true }),
      node("encode", "embed", "dense", { model: "bge-m3" }),
      node("retrieve", "retrieve", "hybrid", { top_k: 10 }),
      node("hydrate", "hydrate", "chunks"),
    ],
    transitions: [ok("normalize", "encode"), ok("encode", "retrieve"), ok("retrieve", "hydrate")],
    bindings: {
      encode: { spec: ref("normalize", "spec") },
      retrieve: { spec: ref("normalize", "spec"), vectors: ref("encode", "vectors") },
      hydrate: { spec: ref("normalize", "spec"), candidates: ref("retrieve", "candidates") },
    },
  };
}

const ids = (blob: GroupBlob) => blob.nodes.map((n) => n.id);
const edges = (blob: GroupBlob) => blob.transitions.map((t) => `${t.from_node_id}>${t.to_node_id}`);

describe("isActionBlob", () => {
  it("is true only for action nodes", () => {
    expect(isActionBlob(node("a", "f", "k"))).toBe(true);
    expect(isActionBlob({ node_type: "group", id: "g", nodes: [], transitions: [], bindings: {} })).toBe(false);
  });
});

describe("setNodeConfigField", () => {
  it("replaces one field of one node's config and leaves the rest of the blob equal", () => {
    const before = defaultBlob();
    const after = setNodeConfigField(before, "retrieve", "top_k", 25);
    expect(after.nodes.find((n) => n.id === "retrieve")).toEqual(node("retrieve", "retrieve", "hybrid", { top_k: 25 }));
    expect(after.nodes.filter((n) => n.id !== "retrieve")).toEqual(before.nodes.filter((n) => n.id !== "retrieve"));
    expect({ ...after, nodes: [] }).toEqual({ ...before, nodes: [] });
  });

  it("adds a field that was absent and keeps the existing ones", () => {
    const after = setNodeConfigField(defaultBlob(), "normalize", "strip_accents", false);
    expect(after.nodes[0]).toEqual(node("normalize", "query", "normalize", { lowercase: true, strip_accents: false }));
  });

  it("stores undefined as the value (the key stays, unlike a delete)", () => {
    const after = setNodeConfigField(defaultBlob(), "retrieve", "top_k", undefined);
    const config = (after.nodes[2] as { config: Record<string, unknown> }).config;
    expect(Object.keys(config)).toEqual(["top_k"]);
    expect(config.top_k).toBeUndefined();
  });

  it("is a content no-op for an unknown node id", () => {
    const before = defaultBlob();
    expect(setNodeConfigField(before, "ghost", "x", 1)).toEqual(before);
  });

  it("does not mutate its input and returns fresh node objects only for the edited node", () => {
    const before = defaultBlob();
    const snapshot = structuredClone(before);
    const after = setNodeConfigField(before, "retrieve", "top_k", 25);
    expect(before).toEqual(snapshot);
    expect(after.nodes[0]).toBe(before.nodes[0]);
    expect(after.nodes[2]).not.toBe(before.nodes[2]);
  });
});

describe("rerank toggle", () => {
  it("reports disabled on the default topology and enabled once spliced in", () => {
    const blob = defaultBlob();
    expect(isRerankEnabled(blob)).toBe(false);
    expect(isRerankEnabled(setRerankEnabled(blob, true))).toBe(true);
  });

  it("enabling splices retrieve -> rerank -> hydrate and rewires hydrate.candidates", () => {
    const after = setRerankEnabled(defaultBlob(), true);
    expect(ids(after)).toEqual(["normalize", "encode", "retrieve", "rerank", "hydrate"]);
    expect(after.nodes[3]).toEqual(node("rerank", "rerank", "cross_encoder"));
    expect(edges(after)).toEqual(["normalize>encode", "encode>retrieve", "retrieve>rerank", "rerank>hydrate"]);
    expect(after.transitions[2]).toEqual(ok("retrieve", "rerank"));
    expect(after.bindings).toEqual({
      encode: { spec: ref("normalize", "spec") },
      retrieve: { spec: ref("normalize", "spec"), vectors: ref("encode", "vectors") },
      rerank: { candidates: ref("retrieve", "candidates"), spec: ref("normalize", "spec") },
      hydrate: { spec: ref("normalize", "spec"), candidates: ref("rerank", "candidates") },
    });
  });

  it("enabling twice returns the very same blob", () => {
    const once = setRerankEnabled(defaultBlob(), true);
    expect(setRerankEnabled(once, true)).toBe(once);
  });

  it("disabling when already off returns the very same blob", () => {
    const blob = defaultBlob();
    expect(setRerankEnabled(blob, false)).toBe(blob);
  });

  it("disabling collapses back to retrieve -> hydrate and restores hydrate.candidates", () => {
    const after = setRerankEnabled(setRerankEnabled(defaultBlob(), true), false);
    expect(after).toEqual(defaultBlob());
  });

  it("appends the rerank node at the end when there is no `retrieve` node", () => {
    const blob: GroupBlob = { ...defaultBlob(), nodes: defaultBlob().nodes.filter((n) => n.id !== "retrieve") };
    expect(ids(setRerankEnabled(blob, true))).toEqual(["normalize", "encode", "hydrate", "rerank"]);
  });

  it("does not mutate its input", () => {
    const before = defaultBlob();
    const snapshot = structuredClone(before);
    setRerankEnabled(before, true);
    expect(before).toEqual(snapshot);
  });
});

describe("query transform select", () => {
  it("reports no transform on the default topology", () => {
    expect(queryTransformKind(defaultBlob())).toBeNull();
  });

  it.each(["rewrite", "hyde"] as const)("selecting %s splices normalize -> %s -> encode and repoints the spec consumers", (kind) => {
    const after = setQueryTransform(defaultBlob(), kind);
    expect(queryTransformKind(after)).toBe(kind);
    expect(ids(after)).toEqual(["normalize", kind, "encode", "retrieve", "hydrate"]);
    expect(after.nodes[1]).toEqual(node(kind, "query", kind));
    expect(edges(after)).toEqual([`encode>retrieve`, "retrieve>hydrate", `normalize>${kind}`, `${kind}>encode`]);
    expect(after.bindings).toEqual({
      [kind]: { spec: ref("normalize", "spec") },
      encode: { spec: ref(kind, "spec") },
      retrieve: { spec: ref(kind, "spec"), vectors: ref("encode", "vectors") },
      hydrate: { spec: ref(kind, "spec"), candidates: ref("retrieve", "candidates") },
    });
  });

  it("selecting the active kind again returns the very same blob", () => {
    const once = setQueryTransform(defaultBlob(), "rewrite");
    expect(setQueryTransform(once, "rewrite")).toBe(once);
  });

  it("selecting null on a blob without transform returns the very same blob", () => {
    const blob = defaultBlob();
    expect(setQueryTransform(blob, null)).toBe(blob);
  });

  it("selecting null removes the transform and restores the original topology", () => {
    const after = setQueryTransform(setQueryTransform(defaultBlob(), "hyde"), null);
    expect(queryTransformKind(after)).toBeNull();
    expect(ids(after)).toEqual(ids(defaultBlob()));
    expect(after.nodes).toEqual(defaultBlob().nodes);
    expect(after.bindings).toEqual(defaultBlob().bindings);
    // Order of transitions: the collapsed normalize>encode is re-appended at the end.
    expect(edges(after)).toEqual(["encode>retrieve", "retrieve>hydrate", "normalize>encode"]);
  });

  it("switching rewrite -> hyde leaves exactly one transform (they are mutually exclusive)", () => {
    const after = setQueryTransform(setQueryTransform(defaultBlob(), "rewrite"), "hyde");
    expect(queryTransformKind(after)).toBe("hyde");
    expect(ids(after)).toEqual(["normalize", "hyde", "encode", "retrieve", "hydrate"]);
    expect(Object.keys(after.bindings).sort()).toEqual(["encode", "hyde", "hydrate", "retrieve"]);
    expect(after.bindings.encode.spec).toEqual(ref("hyde", "spec"));
  });

  it("keeps rerank (its nodes and its own spec binding) across a transform change", () => {
    const withRerank = setRerankEnabled(defaultBlob(), true);
    const after = setQueryTransform(withRerank, "rewrite");
    expect(isRerankEnabled(after)).toBe(true);
    expect(after.bindings.rerank).toEqual({ candidates: ref("retrieve", "candidates"), spec: ref("normalize", "spec") });
    expect(after.bindings.hydrate).toEqual({ spec: ref("rewrite", "spec"), candidates: ref("rerank", "candidates") });
  });

  it("does not mutate its input", () => {
    const before = defaultBlob();
    const snapshot = structuredClone(before);
    setQueryTransform(before, "rewrite");
    expect(before).toEqual(snapshot);
  });
});
