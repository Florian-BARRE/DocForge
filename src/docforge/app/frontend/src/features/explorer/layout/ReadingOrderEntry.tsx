// ====== Code Summary ======
// One IR block in the Layout view's middle column: an index badge (its reading-order position + type
// colour), a type chip, a compact line of extraction facts (page / column / parser confidence /
// language / boilerplate), the native text, and every enrichment applied to it — each showing its
// model CHAIN (which OCR/VLM/LLM ran, provider, latency, and what escalated before it). The card is
// click-SELECTABLE: selecting it lights its box on the page (left), this card, and its chunk (right).

import { useState } from "react";

import type { IRBlock, IREnrichment } from "../../../api/explorer";
import { humanizeEnumOption } from "../../../components/schema-form/fieldLabels";
import { theme } from "../../../theme";
import { displayPage } from "../format";
import { blockStyle } from "./blockColors";

interface ReadingOrderEntryProps {
  block: IRBlock;
  index: number;
  enrichments: IREnrichment[];
  /** This exact block is the current selection — the strongest emphasis. */
  selected: boolean;
  /** This block shares the selected block's chunk (a softer "part of the same group" emphasis). */
  related: boolean;
  /** The parser chain that produced the IR (with fallback outcomes) — e.g. docling ✗ → pp_structure ✓. */
  parseChain?: { kind: string; status: string }[];
  onSelect: () => void;
}

/** The parser chain, showing any fallback: failed parsers struck-through before the one that won. */
function ParserChain({ chain }: { chain: { kind: string; status: string }[] }) {
  return (
    <span
      title="Parser chain that produced this block (failed parsers shown before the one that succeeded)"
      style={{
        display: "inline-flex",
        alignItems: "center",
        gap: 3,
        fontFamily: theme.font.mono,
        fontSize: theme.font.size.xs,
        color: theme.color.dim,
        border: `1px solid ${theme.color.line}`,
        borderRadius: theme.radius.s,
        padding: "0 4px",
      }}
    >
      <span style={{ color: theme.color.mute }}>parsed</span>
      {chain.map((step, i) => {
        // Only an actual "failed" attempt reads as struck-through error ink — "skipped" (a
        // deliberate stop, per brand.md) and "running" (still in flight) are honest, distinct
        // states, not failures, so lumping them in with "failed" would misreport a healthy chain.
        const color =
          step.status === "failed"
            ? theme.color.errorStrong
            : step.status === "skipped"
              ? theme.color.skipStrong
              : step.status === "running"
                ? theme.color.accent
                : theme.color.text;
        return (
          <span key={i} style={{ display: "inline-flex", alignItems: "center", gap: 3 }}>
            {i > 0 && <span style={{ color: theme.color.mute }}>→</span>}
            <span style={{ color, textDecoration: step.status === "failed" ? "line-through" : "none" }}>
              {step.kind}
            </span>
          </span>
        );
      })}
    </span>
  );
}

/** Compact machine-fact line describing HOW this block was extracted and where it sits. */
function ExtractionFacts({ block, parseChain }: { block: IRBlock; parseChain?: { kind: string; status: string }[] }) {
  const facts: string[] = [`p${displayPage(block.page)}`, `#${block.reading_order}`];
  if (block.language) facts.push(block.language);
  return (
    <div style={{ display: "flex", alignItems: "center", gap: theme.space.xs, flexWrap: "wrap" }}>
      {parseChain && parseChain.length > 0 && <ParserChain chain={parseChain} />}
      <span style={{ fontFamily: theme.font.mono, fontSize: theme.font.size.xs, color: theme.color.mute }}>
        {facts.join(" · ")}
      </span>
      {block.is_boilerplate && (
        <span style={{ fontSize: theme.font.size.xs, color: theme.color.skipStrong }}>boilerplate</span>
      )}
    </div>
  );
}

export function ReadingOrderEntry({ block, index, enrichments, selected, related, parseChain, onSelect }: ReadingOrderEntryProps) {
  const [hovered, setHovered] = useState(false);
  const style = blockStyle(block.block_type);
  const borderColor = selected ? theme.color.accent : related || hovered ? theme.color.accentLine : theme.color.line;
  const background = selected ? theme.color.accentSoft : related || hovered ? theme.color.surface2 : theme.color.surface;
  // The left spine is the block's own TYPE colour — the same hue as its box on the page and its
  // segment inside the chunk, so one colour means one thing everywhere; selection promotes it to accent.
  const spine = selected ? theme.color.accent : style.color;
  return (
    <div
      role="button"
      tabIndex={0}
      aria-pressed={selected}
      onClick={onSelect}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
      onKeyDown={(event) => {
        if (event.key === "Enter" || event.key === " ") {
          event.preventDefault();
          onSelect();
        }
      }}
      style={{
        display: "flex",
        flexDirection: "column",
        gap: theme.space.xs,
        padding: theme.space.s,
        paddingLeft: theme.space.m,
        borderRadius: theme.radius.m,
        // Per-side longhand (never the `border` shorthand) so pairing with borderLeft doesn't warn.
        borderTop: `${selected ? 2 : 1}px solid ${borderColor}`,
        borderRight: `${selected ? 2 : 1}px solid ${borderColor}`,
        borderBottom: `${selected ? 2 : 1}px solid ${borderColor}`,
        borderLeft: `4px solid ${spine}`,
        background,
        cursor: "pointer",
        transition: "border-color .1s ease, background .1s ease",
      }}
    >
      <div style={{ display: "flex", alignItems: "center", gap: theme.space.xs }}>
        <span
          style={{
            flex: "none",
            minWidth: 20,
            textAlign: "center",
            fontFamily: theme.font.mono,
            fontSize: theme.font.size.xs,
            fontWeight: theme.font.weight.semibold,
            color: theme.color.onAccent,
            background: style.color,
            borderRadius: theme.radius.s,
            padding: "1px 5px",
          }}
        >
          {index + 1}
        </span>
        <span style={{ fontSize: theme.font.size.xs, fontWeight: theme.font.weight.semibold, color: style.color }}>
          {style.label}
        </span>
      </div>

      <ExtractionFacts block={block} parseChain={parseChain} />

      {block.text && (
        <div style={{ fontSize: theme.font.size.s, color: theme.color.text, whiteSpace: "pre-wrap", wordBreak: "break-word", lineHeight: 1.45 }}>
          {block.text}
        </div>
      )}

      {enrichments.map((enrichment) => (
        <div
          key={enrichment.id}
          style={{
            display: "flex",
            flexDirection: "column",
            gap: 3,
            borderLeft: `2px solid ${theme.color.iris}`,
            paddingLeft: theme.space.s,
            marginTop: 2,
          }}
        >
          <div style={{ display: "flex", alignItems: "center", gap: theme.space.xs, flexWrap: "wrap" }}>
            <span style={{ fontSize: theme.font.size.xs, fontWeight: theme.font.weight.medium, color: theme.color.irisStrong }}>
              {humanizeEnumOption(enrichment.kind)}
            </span>
            {enrichment.status !== "ok" && (
              <span style={{ fontSize: theme.font.size.xs, color: theme.color.errorStrong }}>{enrichment.status}</span>
            )}
          </div>
          {enrichment.text && (
            <span style={{ fontSize: theme.font.size.xs, color: theme.color.dim, whiteSpace: "pre-wrap", wordBreak: "break-word", lineHeight: 1.4 }}>
              {enrichment.text}
            </span>
          )}
        </div>
      ))}
    </div>
  );
}
