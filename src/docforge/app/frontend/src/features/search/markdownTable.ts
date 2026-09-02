// ====== Code Summary ======
// A minimal markdown pipe-table detector for search-hit snippets — chunk text is plain markdown
// (docling's IR output), so a hit landing mid-table shows raw `| Region | Q2 |` rows and a
// `---|---` separator line unless a caller renders them structurally. Pure parsing only, no React.

export interface MarkdownTextBlock {
  type: "text";
  content: string;
}

export interface MarkdownTableBlock {
  type: "table";
  header: string[];
  rows: string[][];
}

export type MarkdownBlock = MarkdownTextBlock | MarkdownTableBlock;

// A GFM table separator row: `---|---`, `:--|--:`, optionally piped/spaced.
const SEPARATOR_ROW = /^\s*\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)*\|?\s*$/;

function isPipeRow(line: string): boolean {
  return line.includes("|") && line.trim().length > 0;
}

function splitRow(line: string): string[] {
  let trimmed = line.trim();
  if (trimmed.startsWith("|")) trimmed = trimmed.slice(1);
  if (trimmed.endsWith("|")) trimmed = trimmed.slice(0, -1);
  return trimmed.split("|").map((cell) => cell.trim());
}

/**
 * Split raw chunk text into alternating plain-text and markdown-table blocks.
 *
 * A pipe row immediately followed by a `---|---`-style separator row starts a table; every
 * consecutive pipe row after that is a body row, until a non-pipe line (or the text ends). Every
 * other line stays untouched plain text, rendered verbatim by the caller.
 *
 * @param text - The raw chunk/snippet text.
 * @returns The ordered blocks — tables structured, everything else as plain text.
 */
export function parseMarkdownBlocks(text: string): MarkdownBlock[] {
  const lines = text.split("\n");
  const blocks: MarkdownBlock[] = [];
  let textBuffer: string[] = [];

  const flushText = () => {
    if (textBuffer.length) {
      blocks.push({ type: "text", content: textBuffer.join("\n") });
      textBuffer = [];
    }
  };

  let i = 0;
  while (i < lines.length) {
    const line = lines[i];
    const next = lines[i + 1];
    if (isPipeRow(line) && next !== undefined && SEPARATOR_ROW.test(next)) {
      flushText();
      const header = splitRow(line);
      let j = i + 2;
      const rows: string[][] = [];
      while (j < lines.length && isPipeRow(lines[j]) && !SEPARATOR_ROW.test(lines[j])) {
        rows.push(splitRow(lines[j]));
        j += 1;
      }
      blocks.push({ type: "table", header, rows });
      i = j;
      continue;
    }
    textBuffer.push(line);
    i += 1;
  }
  flushText();
  return blocks;
}
