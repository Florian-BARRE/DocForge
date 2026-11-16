// ====== Code Summary ======
// Shared "where am I" trail rendered above a page's own tab strip. Every segment but the last is a
// clickable link (calls `navigate` with that segment's View); the last segment is the current
// location — plain ink, `aria-current="page"`, never a link (per brand.md, the accent is reserved
// for the one active/primary action elsewhere on the page, not a breadcrumb tail). A segment
// without a `view` (e.g. a sidebar section label with no page of its own, like "Admin") renders as
// plain text even mid-trail. Long labels (collection names, ids) are CSS-ellipsised with a `title`
// tooltip carrying the full value — brand.md: let names lead, truncate ids.

import type { View } from "./view";
import { theme as t } from "../theme";
import { useNavigate } from "./navigation";

export interface BreadcrumbItem {
  /** Segment text. */
  label: string;
  /** Destination view. Omit for the trailing (current) segment, or for a label with no page of its own. */
  view?: View;
  /** Render the label in the monospace face — reserved for ids/hashes, never prose (brand.md). */
  mono?: boolean;
}

interface BreadcrumbProps {
  items: BreadcrumbItem[];
}

const SEGMENT_MAX_WIDTH = 220;

const segmentBaseStyle = {
  maxWidth: SEGMENT_MAX_WIDTH,
  overflow: "hidden" as const,
  textOverflow: "ellipsis" as const,
  whiteSpace: "nowrap" as const,
  display: "inline-block",
  verticalAlign: "bottom" as const,
};

/** One breadcrumb segment — a steel-toned link for a mid-trail item with a view, plain ink text otherwise. */
function BreadcrumbSegment({ item, isLast }: { item: BreadcrumbItem; isLast: boolean }) {
  const navigate = useNavigate();
  const fontFamily = item.mono ? t.font.mono : t.font.family;

  if (isLast || !item.view) {
    return (
      <span
        style={{ ...segmentBaseStyle, fontFamily, fontSize: t.font.size.s, color: t.color.text, fontWeight: t.font.weight.semibold }}
        aria-current={isLast ? "page" : undefined}
        title={item.label}
      >
        {item.label}
      </span>
    );
  }

  return (
    <button
      type="button"
      onClick={() => navigate(item.view!)}
      title={item.label}
      style={{
        ...segmentBaseStyle, fontFamily, fontSize: t.font.size.s,
        background: "none", border: "none", padding: 0, margin: 0, cursor: "pointer",
        color: t.color.dim,
      }}
    >
      {item.label}
    </button>
  );
}

/**
 * Render a clickable "where am I" trail, e.g. Collections / {collection} / Documents / {file}.
 *
 * Every item but the last is a link; the last is the current page and carries `aria-current="page"`.
 */
export function Breadcrumb({ items }: BreadcrumbProps) {
  return (
    <nav aria-label="Breadcrumb" style={{ display: "flex", alignItems: "center", gap: t.space.xs, flexWrap: "wrap" }}>
      {items.map((item, index) => (
        <span key={index} style={{ display: "inline-flex", alignItems: "center", gap: t.space.xs }}>
          {index > 0 && (
            <span style={{ color: t.color.mute, fontSize: t.font.size.s }} aria-hidden="true">/</span>
          )}
          <BreadcrumbSegment item={item} isLast={index === items.length - 1} />
        </span>
      ))}
    </nav>
  );
}
