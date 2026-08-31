// ====== Code Summary ======
// Pure translation from the grid's local per-column filter state to the API's `DocumentFilter`
// body — the one place that knows which base column each control maps to and how each metadata
// field type serializes to `MetadataFilter` entries (range kinds split into a gte + lte entry).

import type { DocumentFilter, DocumentStatus, MetadataFilter } from "../../api/corpus";
import { apiFieldName, isMetadataColumn, type ColumnFiltersState } from "./types";

function parseNumber(raw: string): number | null {
  if (raw.trim() === "") return null;
  const value = Number(raw);
  return Number.isFinite(value) ? value : null;
}

function toIsoOrNull(raw: string): string | null {
  if (!raw.trim()) return null;
  const date = new Date(raw);
  return Number.isNaN(date.getTime()) ? null : date.toISOString();
}

export function buildDocumentFilter(state: ColumnFiltersState): DocumentFilter {
  const filter: DocumentFilter = {};
  const metadata: MetadataFilter[] = [];

  for (const [columnId, value] of Object.entries(state)) {
    const isMeta = isMetadataColumn(columnId);
    const field = apiFieldName(columnId);

    switch (value.kind) {
      case "text": {
        const contains = value.contains.trim();
        if (!contains) break;
        if (isMeta) metadata.push({ field, op: "contains", value: contains });
        else if (field === "filename") filter.filename = { contains };
        else if (field === "title") filter.title = { contains };
        break;
      }
      case "enumMulti": {
        if (!value.values.length) break;
        if (isMeta) metadata.push({ field, op: "in", value: value.values });
        else if (field === "status") filter.status = value.values as DocumentStatus[];
        else if (field === "format") filter.format = value.values;
        break;
      }
      case "listIn": {
        // Free-typed membership (language, which has no closed enum) or a list-typed metadata
        // field — both express "matches any of these values" via the `in` operator.
        if (!value.values.length) break;
        if (isMeta) metadata.push({ field, op: "in", value: value.values });
        else if (field === "language") filter.language = value.values;
        break;
      }
      case "bool": {
        if (value.value === null) break;
        if (isMeta) metadata.push({ field, op: "eq", value: value.value });
        else if (field === "enabled") filter.enabled = value.value;
        break;
      }
      case "numberRange": {
        const gte = parseNumber(value.gte);
        const lte = parseNumber(value.lte);
        if (gte === null && lte === null) break;
        if (isMeta) {
          if (gte !== null) metadata.push({ field, op: "gte", value: gte });
          if (lte !== null) metadata.push({ field, op: "lte", value: lte });
        } else if (field === "file_size") filter.file_size = { gte: gte ?? undefined, lte: lte ?? undefined };
        else if (field === "page_count") filter.page_count = { gte: gte ?? undefined, lte: lte ?? undefined };
        break;
      }
      case "dateRange": {
        const gte = toIsoOrNull(value.gte);
        const lte = toIsoOrNull(value.lte);
        if (gte === null && lte === null) break;
        if (isMeta) {
          if (gte !== null) metadata.push({ field, op: "gte", value: gte });
          if (lte !== null) metadata.push({ field, op: "lte", value: lte });
        } else if (field === "created_at") filter.created_at = { gte: gte ?? undefined, lte: lte ?? undefined };
        break;
      }
    }
  }

  if (metadata.length) filter.metadata = metadata;
  return filter;
}
