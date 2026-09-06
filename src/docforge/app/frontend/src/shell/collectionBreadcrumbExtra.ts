// ====== Code Summary ======
// Lets a page nested under CollectionShell (e.g. DocumentPage, reached two levels under
// Corpus›Documents) contribute trailing segments to the shell's own breadcrumb, so the shell renders
// ONE unified trail (Collections / {collection} / Corpus / Documents / {filename}) instead of a
// redundant second one stacked below the shell's own "Collections / {collection}". Lives in `shell/`
// (not a feature slice) because both `features/collections` (the provider, CollectionShell) and
// `features/explorer` (a consumer, DocumentPage) need it, and features never cross-import each other.
// Same cross-sibling context pattern as CollectionShell's own `useHideHeaderUpload` — the nested page
// arrives as `children` from App.tsx, a sibling of CollectionShell's own state, so context is the
// only path back up.

import { createContext, useContext, useEffect } from "react";
import type { BreadcrumbItem } from "../components/Breadcrumb";

export const BreadcrumbExtraContext = createContext<((items: BreadcrumbItem[] | null) => void) | null>(null);

/**
 * Contribute trailing breadcrumb segments to the enclosing `CollectionShell`.
 *
 * A no-op outside a `CollectionShell` (context absent), matching `useHideHeaderUpload`'s safety
 * contract for standalone/test rendering.
 *
 * @param items - Trailing segments to append after "Collections / {collection}", memoized by the
 *   caller (a fresh array every render would refire this effect every render) — or null to clear.
 */
export function useCollectionBreadcrumbExtra(items: BreadcrumbItem[] | null): void {
  const setExtra = useContext(BreadcrumbExtraContext);
  useEffect(() => {
    setExtra?.(items);
    return () => setExtra?.(null);
  }, [items, setExtra]);
}
