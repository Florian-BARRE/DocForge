// ====== Code Summary ======
// Type-only parity guard between the hand-written REST mirrors (api/explorer.ts, api/collections.ts,
// api/jobs.ts, api/search.ts) and the backend's real OpenAPI contract (api/generated.ts).
//
// WHY THIS FILE EXISTS: the Layout tab crashed at runtime because `ChunkInfo` (api/explorer.ts) had
// silently drifted behind the backend's actual `ChunkInfo` (missing `heading_path`/`page`) — nothing
// tied the hand-written interface to the real response shape, so the drift was invisible until a
// live page threw. Every `Expect<Equal<...>>` below re-creates that failure mode as a `tsc` error:
// if a backend Pydantic response model gains, loses, or retypes a field, the matching assertion here
// stops compiling, and `npm run build`/CI fails loudly instead of the UI crashing at runtime later.
//
// `generated.ts` is openapi-typescript output (npm run gen:types — requires a reachable backend at
// $OPENAPI_URL, see agent-memory/frontend/gen-types-constraint.md) and is committed as the parity
// BASELINE: CI cannot regenerate it offline, so this file is the frozen reference these checks run
// against. After a backend response model changes: run `npm run gen:types` against a live backend
// to refresh `generated.ts`, THEN `npx tsc --noEmit` — any real drift fails here until the matching
// hand-written interface is brought back in step.
//
// Zero runtime cost: every symbol below is a type alias (erased at compile time). They are exported
// only so `noUnusedLocals` doesn't flag them as dead code — nothing here is ever imported for a
// value, only for the side effect of forcing `tsc` to evaluate the assertion.

import type { components } from "./generated";
import type {
  BulkChunkEnabledPatch,
  BulkChunkEnabledResponse,
  ChunkEnabledPatch,
  ChunkEnabledResult,
  ChunkInfo,
  DocumentDetail,
  DocumentIR,
  DocumentListItem,
  DocumentProvenance,
  IRBlock,
  IREnrichment,
  IRFigure,
  IRTable,
  MetadataValue,
  PageInfo,
} from "./explorer";
import type { AssumptionOverrides, Collection, EstimateOverrides, FieldSpec, ModelRateOverride, RateOverrides } from "./collections";
import type { JobEvent, JobPage, JobStatus, WorkerActivity } from "./jobs";
import type { BlockLocationModel, SearchHitModel } from "./search";

type Schemas = components["schemas"];

// ---------- generic compile-time helpers (type-level only, erased by tsc) ----------

/** Strict (bidirectional) type equality — the standard distributive-conditional identity check. */
type Equal<A, B> = (<T>() => T extends A ? 1 : 2) extends <T>() => T extends B ? 1 : 2 ? true : false;

/** One-directional assignability — `A` can always be used where `B` is expected. */
type AssignableTo<A, B> = [A] extends [B] ? true : false;

/** Fails to compile unless its argument is the literal type `true` — the assertion primitive every
 *  check below resolves through, so a broken assertion surfaces as a `tsc` error on this file. */
export type Expect<T extends true> = T;

/**
 * Recursively (a) strips the "optional key" modifier openapi-typescript emits for any Pydantic
 * field that merely has a default — FastAPI still always serialises the field on a real response
 * (no `exclude_unset`), so "may be omitted" is a codegen artifact, not the real wire shape — and
 * (b) widens a codegen `enum` to the plain string-literal union of its members via the `${T}`
 * template-literal trick, so an enum-backed field compares equal to the hand-written string-literal
 * unions used throughout api/*.ts instead of failing on a cosmetic nominal/enum-vs-union difference.
 *
 * Applied to BOTH sides of every check below (not just the generated side): several hand-written
 * interfaces use an optional key (`field?: X | null`) where the generated schema uses a required key
 * with the same nullable value — stylistically different, identically permissive at the call site.
 * Normalizing both sides means only a REAL field/type drift trips an assertion, never a cosmetic
 * required-vs-optional-key styling choice.
 */
type Normalize<T> = T extends string
  ? `${T}`
  : T extends readonly (infer U)[]
    ? Normalize<U>[]
    : T extends object
      ? { [K in keyof T]-?: Normalize<T[K]> }
      : T;

// ---------- explorer.ts — the IR/Chunk/provenance types that broke the Layout tab ----------

export type _IRBlockParity = Expect<Equal<Normalize<IRBlock>, Normalize<Schemas["IRBlock"]>>>;
export type _IRTableParity = Expect<Equal<Normalize<IRTable>, Normalize<Schemas["IRTable"]>>>;
export type _IRFigureParity = Expect<Equal<Normalize<IRFigure>, Normalize<Schemas["IRFigure"]>>>;
export type _IREnrichmentParity = Expect<Equal<Normalize<IREnrichment>, Normalize<Schemas["IREnrichment"]>>>;
export type _DocumentIRParity = Expect<Equal<Normalize<DocumentIR>, Normalize<Schemas["DocumentIRModel"]>>>;
export type _DocumentProvenanceParity = Expect<Equal<Normalize<DocumentProvenance>, Normalize<Schemas["DocumentProvenance"]>>>;
export type _MetadataValueParity = Expect<Equal<Normalize<MetadataValue>, Normalize<Schemas["MetadataValue"]>>>;
export type _PageInfoParity = Expect<Equal<Normalize<PageInfo>, Normalize<Schemas["PageInfo"]>>>;
export type _DocumentDetailParity = Expect<Equal<Normalize<DocumentDetail>, Normalize<Schemas["DocumentDetail"]>>>;
export type _DocumentListItemParity = Expect<Equal<Normalize<DocumentListItem>, Normalize<Schemas["DocumentListItem"]>>>;
export type _ChunkEnabledPatchParity = Expect<Equal<Normalize<ChunkEnabledPatch>, Normalize<Schemas["ChunkEnabledPatch"]>>>;
export type _BulkChunkEnabledPatchParity = Expect<Equal<Normalize<BulkChunkEnabledPatch>, Normalize<Schemas["BulkChunkEnabledPatch"]>>>;
// Caught by this guard (2026-09): both response shapes were missing `search_sync_pending` /
// `search_sync_error` — fixed in api/explorer.ts as part of adding this file (real drift, not a
// hypothetical one).
export type _ChunkEnabledResultParity = Expect<Equal<Normalize<ChunkEnabledResult>, Normalize<Schemas["ChunkEnabledResult"]>>>;
export type _BulkChunkEnabledResponseParity = Expect<
  Equal<Normalize<BulkChunkEnabledResponse>, Normalize<Schemas["BulkChunkEnabledResponse"]>>
>;

// `ChunkInfo.role` is DELIBERATELY narrower than the backend contract: the backend's Pydantic field
// is a plain `str` (the OpenAPI schema carries no enum), while the client narrows it to the 4 values
// the pipeline actually assigns (see the `ChunkRole` doc comment in api/explorer.ts). Assert the
// shared subset in the direction that matters — every OTHER field must still match exactly, and
// `ChunkRole` must remain assignable to `string` (so a real response is never rejected) — rather
// than a full equality that would permanently fail on this one intentional narrowing.
export type _ChunkInfoParity = Expect<Equal<Normalize<Omit<ChunkInfo, "role">>, Normalize<Omit<Schemas["ChunkInfo"], "role">>>>;
export type _ChunkInfoRoleStillAString = Expect<AssignableTo<ChunkInfo["role"], string>>;

// ---------- collections.ts — Collection + its nested field-schema/estimate-override types ----------

export type _FieldSpecParity = Expect<Equal<Normalize<FieldSpec>, Normalize<Schemas["FieldSpecModel"]>>>;
export type _ModelRateOverrideParity = Expect<Equal<Normalize<ModelRateOverride>, Normalize<Schemas["ModelRateOverride"]>>>;
export type _RateOverridesParity = Expect<Equal<Normalize<RateOverrides>, Normalize<Schemas["RateOverrides"]>>>;

// `AssumptionOverrides` DELIBERATELY omits `target_chunk_tokens`/`chunk_overlap_ratio` — the
// collection's actual chunker config always wins on top for those two (see EstimateOverrideMerger),
// so exposing an override here would silently do nothing (comment already on the type in
// api/collections.ts). Assert only that a REAL backend payload always satisfies the narrower client
// type (the safe direction — reading a real response through this type never drops required data
// or crashes); full equality would permanently fail on this one intentional omission.
export type _AssumptionOverridesSafeToRead = Expect<AssignableTo<Normalize<Schemas["AssumptionOverrides"]>, Normalize<AssumptionOverrides>>>;

// `EstimateOverrides.assumptions` carries the above narrowing one level down, so it is excluded from
// the equality check the same way and covered by the same directional assertion.
export type _EstimateOverridesParity = Expect<
  Equal<Normalize<Omit<EstimateOverrides, "assumptions">>, Normalize<Omit<Schemas["EstimateOverrides"], "assumptions">>>
>;
export type _EstimateOverridesAssumptionsSafeToRead = Expect<
  AssignableTo<Normalize<Schemas["EstimateOverrides"]>["assumptions"], Normalize<EstimateOverrides>["assumptions"]>
>;

// `Collection.fields`/`estimate_overrides` are checked above as their own named types; exclude them
// here to avoid re-deriving the same (already-asserted) narrowing failure through the parent object.
export type _CollectionParity = Expect<
  Equal<
    Normalize<Omit<Collection, "fields" | "estimate_overrides">>,
    Normalize<Omit<Schemas["CollectionModel"], "fields" | "estimate_overrides">>
  >
>;

// ---------- jobs.ts — JobStatus / JobPage / WorkerActivity + the JobEvent trace row ----------

export type _JobEventParity = Expect<Equal<Normalize<JobEvent>, Normalize<Schemas["JobEvent"]>>>;
export type _JobStatusParity = Expect<Equal<Normalize<JobStatus>, Normalize<Schemas["JobStatus"]>>>;
export type _JobPageParity = Expect<Equal<Normalize<JobPage>, Normalize<Schemas["JobPage"]>>>;
export type _WorkerActivityParity = Expect<Equal<Normalize<WorkerActivity>, Normalize<Schemas["WorkerActivity"]>>>;

// ---------- search.ts — the search hit model ----------

export type _BlockLocationModelParity = Expect<Equal<Normalize<BlockLocationModel>, Normalize<Schemas["BlockLocationModel"]>>>;
export type _SearchHitModelParity = Expect<Equal<Normalize<SearchHitModel>, Normalize<Schemas["SearchHitModel"]>>>;
