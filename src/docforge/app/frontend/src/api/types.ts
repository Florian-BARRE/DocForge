// ====== Code Summary ======
// TypeScript mirror of the pipeline design API contract. These types are the ONLY place the
// backend payload shapes are written down — every component consumes them, nothing re-declares.

// ---------- describe layer (palette) ----------

export interface IoSlot {
  name: string;
  artefact_type: string;
  required: boolean;
  description: string | null;
}

export interface NodeCard {
  kind: string;
  node_type: string;
  name: string;
  summary: string;
  how_it_works: string | null;
  config_schema: JsonSchema;
  consumes: IoSlot[];
  produces: IoSlot[];
  error_policy: string;
  unique_in_graph: boolean;
  /** True when this node's output carries a score a downstream `score_below` edge can read. */
  scored: boolean;
  /** Field name -> its possible values, for ready-made `when_equals` branches (e.g. a classifier's "kind"). */
  switch_fields: Record<string, string[]>;
}

/** A family's composition rule — how many of its nodes may coexist in one graph. */
export type FamilyMode = "exclusive" | "stackable" | "chain" | "stage";

export interface FamilyCatalog {
  family: string;
  title: string;
  description: string;
  mode: FamilyMode;
  nodes: NodeCard[];
}

export interface Palette {
  families: FamilyCatalog[];
  /** The wire payload also carries `run_inputs` / `mechanics` / `artefacts` — advanced palette
   *  blocks, null unless the design GET is called with `?full=true`. The product UI never
   *  consumes them, so they are deliberately not mirrored here. */
}

// ---------- JSON Schema (the subset the generic form renderer needs) ----------

export interface JsonSchemaProperty {
  type?: string;
  title?: string;
  description?: string;
  default?: unknown;
  enum?: string[];
  minimum?: number;
  maximum?: number;
  /** Pydantic's `gt=`/`lt=` constraints — treated as a soft bound alongside minimum/maximum. */
  exclusiveMinimum?: number;
  exclusiveMaximum?: number;
  format?: string;
  items?: JsonSchemaProperty;
  /** Pydantic's `X | None` shape — collapsed by `SchemaField.deref` into the non-null branch. */
  anyOf?: JsonSchemaProperty[];
  $ref?: string;
  allOf?: { $ref?: string }[];
}

export interface JsonSchema {
  properties?: Record<string, JsonSchemaProperty>;
  required?: string[];
  $defs?: Record<string, JsonSchemaProperty>;
  [key: string]: unknown;
}

// ---------- blob layer (the editable truth) ----------

export type Binding =
  | { source: "run"; field_name: string }
  | { source: "node"; node_id: string; field_name: string }
  | { source: "group"; field_name: string }
  | { source: "first"; candidates: { source: "node"; node_id: string; field_name: string }[] };

export interface Condition {
  kind: string;
  [param: string]: unknown; // condition params (threshold, field, equals…) come from mechanics
}

export interface Transition {
  from_node_id: string;
  to_node_id: string;
  condition?: Condition;
}

export interface ActionBlob {
  node_type: "action";
  id: string;
  family: string;
  kind: string;
  config: Record<string, unknown>;
}

export interface GroupBlob {
  node_type: "group";
  id: string;
  nodes: NodeBlob[];
  transitions: Transition[];
  bindings: Record<string, Record<string, Binding>>;
}

export interface ForEachBlob {
  node_type: "foreach";
  id: string;
  over: Binding;
  item_field: string;
  max_concurrency: number;
  body: GroupBlob;
}

export type NodeBlob = ActionBlob | GroupBlob | ForEachBlob;

// ---------- inspect layer ----------

export interface ValidationIssue {
  code: string;
  location: string;
  message: string;
}

export interface DesignResponse {
  palette: Palette;
  blob: GroupBlob;
  issues: ValidationIssue[];
}

/** Advanced-surface response (headless — the product UI no longer calls /inspect). The wire
 *  payload also carries `explored` (the described tree), deliberately not mirrored here. */
export interface InspectResponse {
  valid: boolean;
  issues: ValidationIssue[];
  build_error: string | null;
}

// ---------- edit layer (server-side graph operations) ----------

/** Path of foreach/group node ids from the root to the container to edit; [] = root. */
export type ContainerIdPath = string[];

export interface AddNodeOp {
  op: "add_node";
  family: string;
  kind: string;
  /** Explicit graph-unique id; when absent the server derives a fresh id from kind. */
  node_id?: string | null;
  container: ContainerIdPath;
}

export interface AddLoopOp {
  op: "add_loop";
  /** The upstream list field the loop iterates. */
  over: Binding;
  node_id?: string | null;
  item_field?: string;
  max_concurrency?: number;
  container: ContainerIdPath;
}

export interface RemoveNodeOp {
  op: "remove_node";
  node_id: string;
  container: ContainerIdPath;
}

export interface SetBindingOp {
  op: "set_binding";
  node_id: string;
  slot: string;
  /** null unbinds the slot (a no-op if it was already unset). */
  binding: Binding | null;
  container: ContainerIdPath;
}

export interface SetAfterOp {
  op: "set_after";
  node_id: string;
  /** New predecessor; the incoming edge's condition is preserved. Null detaches. */
  from_node_id: string | null;
  container: ContainerIdPath;
}

export interface SetConditionOp {
  op: "set_condition";
  from_node_id: string;
  to_node_id: string;
  condition: Condition;
  container: ContainerIdPath;
}

export interface SetConfigOp {
  op: "set_config";
  node_id: string;
  /** Full replacement, not a merge. */
  config: Record<string, unknown>;
  container: ContainerIdPath;
}

export interface SetLoopPropOp {
  op: "set_loop_prop";
  node_id: string;
  item_field?: string | null;
  max_concurrency?: number | null;
  over?: Binding | null;
  container: ContainerIdPath;
}

export interface InsertFragmentOp {
  op: "insert_fragment";
  /** The recipe group whose CONTENTS are spliced in (its wrapper group is discarded). */
  fragment: GroupBlob;
  /** Preferred new ids per original fragment id; collisions still get _N suffixes. */
  overrides?: Record<string, string>;
  container: ContainerIdPath;
}

export type EditOperation =
  | AddNodeOp
  | AddLoopOp
  | RemoveNodeOp
  | SetBindingOp
  | SetAfterOp
  | SetConditionOp
  | SetConfigOp
  | SetLoopPropOp
  | InsertFragmentOp;

/** Advanced-surface response (the edit client is kept for a future advanced mode). The wire
 *  payload also carries `explored` (the described tree), deliberately not mirrored here. */
export interface EditResponse {
  blob: GroupBlob;
  valid: boolean;
  issues: ValidationIssue[];
  /** Set when an operation was impossible, or the edited result was unbuildable; blob is then
   *  either the original (impossible op) or the edited-but-unbuildable blob, echoed as-is. */
  edit_error: string | null;
}

// ---------- stage rail layer (the simple, fixed-shape product view) ----------

/** How the user interacts with a stage — what editor face the rail renders for it. */
export type StageKind = "fixed" | "toggle" | "provider" | "stack";

/** One provider in a fallback chain — a single model-call attempt. Every step falls through to
 *  the next on failure; `score_below` adds a quality escalation. The last step has the final say. */
export interface ChainStep {
  kind: string;
  config: Record<string, unknown>;
  score_below: number | null;
}

/** A fallback chain the user can build at one model-call site of a stage — a chain-capable
 *  provider/toggle stage's OWN chain (parse, embed, metagen chunk/document; `slot` equals the
 *  stage's own `key`, and the action to edit it must be sent with `slot: null`), or one of
 *  enrich's per-figure-class sites (`slot` is the branch key, e.g. `scanned_text_ocr`). The
 *  contextualize `llm` method's chain is ALSO surfaced here (`slot: "contextualize.{index}"`) for
 *  read/display purposes only — it is edited through the stack's `StackMethod.chain`, never a
 *  direct `set_chain` (the compiler only recognises `stage="enrich"` slot edits). Flagged with its
 *  family so the UI can colour it apart from the linear rail. */
export interface ChainView {
  slot: string;
  title: string;
  description: string;
  family: string;
  available: string[];
  steps: ChainStep[];
}

/** A fallback chain's canonical state — its family and its ordered steps. Carried inline by a
 *  StackMethod (the `llm` method's own chain) rather than addressed by a chain-list slot. */
export interface ChainSpec {
  family: string;
  steps: ChainStep[];
}

/** One method of a stackable stage (contextualize) — a node in the ordered composition. A simple
 *  method (doc_meta, breadcrumb, sliding) carries no chain; `llm` additionally carries the generic-
 *  `llm` fallback chain its ForEach body runs, edited in place through `set_stack` (the chain is
 *  part of the method, not a separate slot-addressed `set_chain` edit). */
export interface StackMethod {
  kind: string;
  config: Record<string, unknown>;
  chain?: ChainSpec | null;
}

/** The product-level view of one pipeline stage — everything the rail renders for it. */
export interface StageView {
  key: string;
  title: string;
  description: string;
  kind: StageKind;
  enabled: boolean;
  removable: boolean;
  family: string | null;
  provider: string | null;
  available: string[];
  config: Record<string, unknown> | null;
  chains: ChainView[];
  stack: StackMethod[];
  requires: string[];
  notes: string | null;
}

/** The rail's one-call open: the ordered stage skeleton PLUS the blob's validity verdict
 *  (an unbuildable blob is DATA — valid=false + build_error — never an HTTP error). */
export interface StageViewResponse {
  stages: StageView[];
  valid: boolean;
  issues: ValidationIssue[];
  build_error: string | null;
}

export interface StageApplyResponse {
  blob: GroupBlob;
  stages: StageView[];
  valid: boolean;
  issues: ValidationIssue[];
  /** What the compiler did beyond the literal action (dependency cascades, ignored no-ops). */
  notices: string[];
}

/** The discriminated union of every stage-level mutation the rail can send — ONE per `/apply`
 *  round-trip, mirroring the backend's own `StageAction` union. */
export type StageAction =
  | { action: "enable_stage"; stage: string }
  | { action: "disable_stage"; stage: string }
  | { action: "set_provider"; stage: string; kind: string }
  | { action: "set_config"; stage: string; node?: string | null; config: Record<string, unknown> }
  | { action: "set_chain"; stage: string; slot: string | null; steps: ChainStep[] }
  | { action: "set_stack"; stage: string; steps: StackMethod[] };
