// ====== Code Summary ======
// The IR block-type → colour + label map for the Layout view (page render with colour-coded block
// boxes + a matching reading-order panel). Every colour is a THEME token (never a raw hex, per
// brand.md) — a distinct hue per structural role so a glance at a page tells title from text from
// table from figure. Unknown types fall back to the neutral capability steel with a humanised label.

import { theme } from "../../../theme";

export interface BlockStyle {
  color: string;
  label: string;
}

// Keyed by the raw ``block_type`` (lower-cased). Several docling types collapse onto one role/colour
// (e.g. title + section_header → "Heading") so the legend stays short and legible.
// Vivid IR-type palette (theme.color.ir.*), NEVER the forge accent — orange is reserved for the
// ACTIVE/selected state across the whole Layout view, so a plain heading must never read as "active".
// Content types are saturated (red / gold / emerald / violet / magenta); furniture types (text /
// caption / header) stay quiet so colour lands where the meaning is.
const STYLES: Record<string, BlockStyle> = {
  title: { color: theme.color.ir.heading, label: "Heading" },
  section_header: { color: theme.color.ir.heading, label: "Heading" },
  heading: { color: theme.color.ir.heading, label: "Heading" },
  text: { color: theme.color.ir.text, label: "Text" },
  paragraph: { color: theme.color.ir.text, label: "Text" },
  list_item: { color: theme.color.ir.list, label: "List" },
  list: { color: theme.color.ir.list, label: "List" },
  table: { color: theme.color.ir.table, label: "Table" },
  picture: { color: theme.color.ir.figure, label: "Figure" },
  figure: { color: theme.color.ir.figure, label: "Figure" },
  image: { color: theme.color.ir.figure, label: "Figure" },
  caption: { color: theme.color.ir.caption, label: "Caption" },
  formula: { color: theme.color.ir.formula, label: "Formula" },
  equation: { color: theme.color.ir.formula, label: "Formula" },
  code: { color: theme.color.ir.caption, label: "Code" },
  page_header: { color: theme.color.ir.chrome, label: "Header / footer" },
  page_footer: { color: theme.color.ir.chrome, label: "Header / footer" },
  header_footer: { color: theme.color.ir.chrome, label: "Header / footer" },
  footnote: { color: theme.color.ir.chrome, label: "Footnote" },
};

/** Humanise an unmapped raw type ("some_kind" → "Some kind") for its fallback label. */
function humanize(raw: string): string {
  const spaced = raw.replace(/[_-]+/g, " ").trim();
  return spaced ? spaced.charAt(0).toUpperCase() + spaced.slice(1) : "Block";
}

export function blockStyle(blockType: string): BlockStyle {
  return STYLES[blockType.toLowerCase()] ?? { color: theme.color.ir.text, label: humanize(blockType) };
}

// The distinct legend entries, in a sensible reading order (structure → prose → objects → chrome).
export const BLOCK_LEGEND: BlockStyle[] = [
  { color: theme.color.ir.heading, label: "Heading" },
  { color: theme.color.ir.text, label: "Text" },
  { color: theme.color.ir.list, label: "List" },
  { color: theme.color.ir.table, label: "Table" },
  { color: theme.color.ir.figure, label: "Figure" },
  { color: theme.color.ir.caption, label: "Caption / code" },
  { color: theme.color.ir.formula, label: "Formula" },
  { color: theme.color.ir.chrome, label: "Header / footer" },
];
