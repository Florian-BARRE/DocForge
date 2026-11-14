// ====== Code Summary ======
// Facade of the collections API — re-exports every name the former single `api/collections.ts`
// module exposed, so `from "../api/collections"` keeps resolving unchanged.

export * from "./schema";
export * from "./types";
export * from "./client";
export * from "./health";
export * from "./estimate";
