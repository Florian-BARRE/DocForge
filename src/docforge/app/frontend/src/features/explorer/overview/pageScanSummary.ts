// ====== Code Summary ======
// Pure derivation over an already-loaded PageInfo[] — how many pages were scanned vs. digital-born,
// and which page languages diverge from the document's own resolved language. No fetch, no IR: the
// System metadata panel's "Content" group is meant to stay cheap.

import type { PageInfo } from "../../../api/explorer";

export interface PageScanSummary {
  scanned: number;
  total: number;
  /** Distinct page-level languages that differ from the document's own `language` — empty when
   *  every page agrees (or none reported a language at all). */
  otherLanguages: string[];
}

export function summarizePageScans(pages: PageInfo[], documentLanguage: string | null): PageScanSummary {
  const scanned = pages.filter((page) => page.is_scanned).length;
  const otherLanguages = Array.from(
    new Set(pages.map((page) => page.language).filter((lang): lang is string => Boolean(lang) && lang !== documentLanguage)),
  );
  return { scanned, total: pages.length, otherLanguages };
}
