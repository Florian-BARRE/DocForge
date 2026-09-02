// ====== Code Summary ======
// A search hit's chunk text — like the explorer's `ChunkText`, but a local copy (see
// `[[feature-slice-isolation]]`) that additionally renders any embedded markdown pipe table as a
// real `<table>` instead of raw `| a | b |` / `---|---` lines. Collapsing to a few lines only
// applies to plain text — a table is always shown in full, since line-clamping a table's DOM
// doesn't produce anything legible.

import { useState } from "react";
import { theme } from "../../theme";
import { parseMarkdownBlocks, type MarkdownBlock } from "./markdownTable";

const COLLAPSED_LINE_CLAMP = 6;
const LONG_TEXT_THRESHOLD = 480;

function MarkdownTable({ block }: { block: Extract<MarkdownBlock, { type: "table" }> }) {
  return (
    <table
      style={{
        borderCollapse: "collapse", width: "100%", margin: `${theme.space.xs}px 0`,
        fontSize: theme.font.size.xs,
      }}
    >
      <thead>
        <tr>
          {block.header.map((cell, i) => (
            <th
              key={i}
              style={{
                textAlign: "left", padding: "4px 8px", borderBottom: `2px solid ${theme.color.line}`,
                color: theme.color.dim, fontWeight: theme.font.weight.semibold, whiteSpace: "nowrap",
              }}
            >
              {cell}
            </th>
          ))}
        </tr>
      </thead>
      <tbody>
        {block.rows.map((row, ri) => (
          <tr key={ri}>
            {row.map((cell, ci) => (
              <td key={ci} style={{ padding: "4px 8px", borderBottom: `1px solid ${theme.color.line}`, color: theme.color.text }}>
                {cell}
              </td>
            ))}
          </tr>
        ))}
      </tbody>
    </table>
  );
}

export function SearchHitText({ text }: { text: string }) {
  const [expanded, setExpanded] = useState(false);
  const blocks = parseMarkdownBlocks(text);
  const hasTable = blocks.some((block) => block.type === "table");
  const isLong = !hasTable && (text.split("\n").length > COLLAPSED_LINE_CLAMP || text.length > LONG_TEXT_THRESHOLD);
  const clamp = expanded || !isLong;

  return (
    <div>
      <div
        style={{
          fontSize: theme.font.size.s, color: theme.color.text, lineHeight: 1.6,
          display: clamp ? "block" : "-webkit-box",
          WebkitLineClamp: clamp ? undefined : COLLAPSED_LINE_CLAMP,
          WebkitBoxOrient: "vertical",
          overflow: clamp ? "visible" : "hidden",
        }}
      >
        {blocks.map((block, i) =>
          block.type === "table" ? (
            <MarkdownTable key={i} block={block} />
          ) : (
            <span key={i} style={{ whiteSpace: "pre-wrap" }}>{block.content}</span>
          ),
        )}
      </div>
      {isLong && (
        <button
          onClick={() => setExpanded((v) => !v)}
          style={{
            background: "none", border: "none", color: theme.color.accent, cursor: "pointer",
            fontSize: theme.font.size.xs, fontWeight: 600, padding: 0, marginTop: 6,
          }}
        >
          {expanded ? "show less" : "show more"}
        </button>
      )}
    </div>
  );
}
